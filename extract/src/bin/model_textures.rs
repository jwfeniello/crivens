//! Decode textures to PNG without the full ModelDescriptor parse.
//! usage: model_textures [--redo=0x12,0x1e] <Model__dir | Texture__dir>...
//!   Model__ dirs: writes imageN.png for each embedded texture (skips existing unless its
//!   format is listed in --redo). Texture__ dirs: rewrites texture.png if its format is in --redo.
use std::{
    fs,
    panic::{AssertUnwindSafe, catch_unwind},
    path::Path,
};

use bnl::asset::{AssetDescriptor, Dump, texture::{Texture, TextureDescriptor}};

fn u32le(b: &[u8], o: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(o..o + 4)?.try_into().ok()?))
}

fn read_res(dir: &Path) -> Vec<u8> {
    // large background models have dozens of resource chunks
    (0..)
        .map_while(|i| fs::read(dir.join(format!("resource{i}"))).ok())
        .flatten()
        .collect()
}

fn decode(desc: &[u8], res: &[u8], out: &Path) -> Result<(), String> {
    match catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let td = TextureDescriptor::from_bytes(desc).map_err(|e| format!("{e}"))?;
        let (o, s) = (td.texture_offset() as usize, td.texture_size() as usize);
        if s == 0 {
            // runtime render target (e.g. screen capture for page-turn transitions): no pixels
            return Err("render target with no data".into());
        }
        let bytes = res.get(o..o + s).ok_or("texture data out of range")?.to_vec();
        Texture::new(td, bytes).dump(out).map_err(|e| e.to_string())
    })) {
        Ok(r) => r,
        Err(_) => Err("panic".into()),
    }
}

fn run_model(dir: &Path, redo: &[u32]) -> Result<usize, String> {
    let desc = fs::read(dir.join("descriptor")).map_err(|e| e.to_string())?;
    let res = read_res(dir);
    let footer = u32le(&desc, 0).ok_or("short")? as usize;
    let n = u32le(&desc, 4).ok_or("short")? as usize;
    let mut written = 0;
    for e in 0..n {
        let ty = u32le(&desc, footer + 8 * e).ok_or("footer")?;
        let ptr = u32le(&desc, footer + 8 * e + 4).ok_or("footer")? as usize;
        if ty != 7 {
            continue;
        }
        let count = u32le(&desc, ptr).ok_or("tex count")? as usize;
        let list = u32le(&desc, ptr + 4).ok_or("tex list")? as usize;
        for i in 0..count {
            let out = dir.join(format!("image{i}.png"));
            let tp = u32le(&desc, list + 4 * i).ok_or("tex ptr")? as usize;
            let fmt = u32le(&desc, tp).unwrap_or(0);
            if out.exists() && !redo.contains(&fmt) {
                continue;
            }
            match decode(&desc[tp..], &res, &out) {
                Ok(()) => written += 1,
                Err(e) => eprintln!("{} image{i} (fmt {fmt:#x}): {e}", dir.display()),
            }
        }
    }
    Ok(written)
}

fn run_texture(dir: &Path, redo: &[u32]) -> Result<usize, String> {
    let desc = fs::read(dir.join("descriptor")).map_err(|e| e.to_string())?;
    let fmt = u32le(&desc, 0).ok_or("short")?;
    let out = dir.join("texture.png");
    if out.exists() && !redo.contains(&fmt) {
        return Ok(0);
    }
    // Texture asset resources hold the pixel data from offset 0
    let res = read_res(dir);
    decode(&desc, &res, &out).map(|_| 1).map_err(|e| format!("fmt {fmt:#x}: {e}"))
}

fn main() {
    let mut redo = vec![];
    let mut total = 0;
    for a in std::env::args().skip(1) {
        if let Some(list) = a.strip_prefix("--redo=") {
            redo = list
                .split(',')
                .filter_map(|s| u32::from_str_radix(s.trim_start_matches("0x"), 16).ok())
                .collect();
            continue;
        }
        let p = Path::new(&a);
        let name = p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let r = if name.starts_with("Texture__") { run_texture(p, &redo) } else { run_model(p, &redo) };
        match r {
            Ok(n) => total += n,
            Err(e) => eprintln!("{a}: {e}"),
        }
    }
    println!("wrote {total} images");
}
