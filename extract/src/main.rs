//! Extracts Grabbed by the Ghoulies assets using the luboise/bnl library.
//! usage: ghoul_extract <iso_root> <out_dir> <hashes.txt>
use std::{
    collections::HashMap,
    fs,
    panic::{AssertUnwindSafe, catch_unwind},
    path::{Path, PathBuf},
};

use bnl::{
    AssetMetadata, BNLFile, RawAsset,
    asset::{
        AssetType, Dump, aidlist::AidList, font::Font, loctext::LoctextResource,
        model::gltf::GLTFModel, texture::Texture,
    },
};

#[derive(Default)]
struct Stats {
    ok: HashMap<String, usize>,
    fail: HashMap<String, usize>,
    raw: usize,
}

fn u32le(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn safe<T>(f: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(r) => r,
        Err(_) => Err("panic in decoder".into()),
    }
}

/// Convert one asset into a viewable format inside `dir`, for the types the library can decode.
fn convert(raw: &RawAsset, dir: &Path, st: &mut Stats, log: &mut Vec<String>) {
    let ty = raw.metadata().asset_type();
    let kind = ty.to_string();
    let r: Option<Result<(), String>> = match ty {
        AssetType::ResTexture => Some(safe(|| {
            let a = raw.clone().to_asset::<Texture>().map_err(|e| format!("{e}"))?;
            a.asset().dump(dir.join("texture.png")).map_err(|e| e.to_string())
        })),
        AssetType::ResModel => Some(safe(|| {
            let a = raw.clone().to_asset::<GLTFModel>().map_err(|e| format!("{e}"))?;
            a.asset().dump(dir.join("model.gltf")).map_err(|e| e.to_string())
        })),
        AssetType::ResAidList => Some(safe(|| {
            let a = raw.clone().to_asset::<AidList>().map_err(|e| format!("{e}"))?;
            a.asset().dump(dir.join("aidlist.txt")).map_err(|e| e.to_string())
        })),
        AssetType::ResFont => Some(safe(|| {
            let a = raw.clone().to_asset::<Font>().map_err(|e| format!("{e}"))?;
            let gdir = dir.join("glyphs");
            fs::create_dir_all(&gdir).map_err(|e| e.to_string())?;
            for g in &a.asset().glyphs {
                for (v, t) in g.textures.iter().enumerate() {
                    let _ = t.dump(gdir.join(format!("glyph_{:05}_v{}.png", g.glyph_index, v)));
                }
            }
            Ok(())
        })),
        _ => None,
    };
    if let Some(r) = r {
        match r {
            Ok(()) => *st.ok.entry(kind).or_default() += 1,
            Err(e) => {
                *st.fail.entry(kind.clone()).or_default() += 1;
                log.push(format!("{} [{}]: {}", dir.display(), kind, e));
            }
        }
    }
}

fn write_raw(raw: &RawAsset, dir: &Path) {
    let _ = fs::write(dir.join("metadata"), raw.metadata().to_bytes());
    let _ = fs::write(dir.join("descriptor"), raw.descriptor_bytes());
    if let Some(chunks) = raw.resource_chunks() {
        for (i, c) in chunks.iter().enumerate() {
            let _ = fs::write(dir.join(format!("resource{i}")), c);
        }
    }
}

/// Loose demand/font asset files use the same descriptor + dataview layout as BNL entries.
fn loose_to_raw(bytes: &[u8], name: &str) -> Option<RawAsset> {
    if bytes.len() < 0x28 {
        return None;
    }
    let ty = AssetType::try_from(u32le(bytes, 0)).ok()?;
    let (dp, ds, vp, rs) = (
        u32le(bytes, 0x10) as usize,
        u32le(bytes, 0x14) as usize,
        u32le(bytes, 0x18) as usize,
        u32le(bytes, 0x1c) as usize,
    );
    let desc = bytes.get(dp..dp + ds)?.to_vec();
    let chunks = if rs == 0 {
        None
    } else {
        let buf = bytes.get(vp..vp + rs)?;
        let nviews = u32le(buf, 4) as usize;
        let mut v = vec![];
        for i in 0..nviews {
            let o = u32le(buf, 8 + i * 8) as usize;
            let s = u32le(buf, 12 + i * 8) as usize;
            v.push(buf.get(o..o + s)?.to_vec());
        }
        Some(v)
    };
    let short: String = name.chars().take(120).collect();
    Some(RawAsset::new(AssetMetadata::new(&short, ty, 0, 0), desc, chunks))
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let root = PathBuf::from(&a[1]);
    let out = PathBuf::from(&a[2]);
    let hashes: HashMap<String, String> = fs::read_to_string(&a[3])
        .unwrap_or_default()
        .lines()
        .filter_map(|l| {
            let p: Vec<&str> = l.split(',').collect();
            if p.len() < 3 || p[2].is_empty() {
                return None;
            }
            let h = u32::from_str_radix(p[0].trim_start_matches("0x"), 16).ok()?;
            Some((format!("{h:08x}"), p[2].trim().to_string()))
        })
        .collect();
    let resolve = |f: &str| hashes.get(&f.to_lowercase()).cloned().unwrap_or_else(|| f.to_string());

    let mut st = Stats::default();
    let mut log = vec![];

    // 1. Bundles
    for e in walkdir::WalkDir::new(root.join("bundles")).into_iter().filter_map(|e| e.ok()) {
        let p = e.path();
        if p.extension().and_then(|x| x.to_str()) != Some("bnl") {
            continue;
        }
        let rel = p.strip_prefix(&root).unwrap().with_extension("");
        let bytes = fs::read(p).unwrap();
        let bnl = match safe(|| BNLFile::from_bytes(&bytes).map_err(|e| format!("{e:?}"))) {
            Ok(b) => b,
            Err(e) => {
                log.push(format!("BNL FAIL {}: {e}", p.display()));
                continue;
            }
        };
        println!("{} ({} assets)", rel.display(), bnl.get_raw_assets().len());
        for raw in bnl.get_raw_assets() {
            let dir = out.join(&rel).join(format!("{}__{}", raw.metadata().asset_type(), raw.name()));
            fs::create_dir_all(&dir).unwrap();
            write_raw(raw, &dir);
            st.raw += 1;
            convert(raw, &dir, &mut st, &mut log);
        }
    }

    // 2. Loose assets in demand/ and font/
    for sub in ["demand", "font"] {
        for e in fs::read_dir(root.join(sub)).unwrap().filter_map(|e| e.ok()) {
            let fname = e.file_name().to_string_lossy().to_string();
            let bytes = fs::read(e.path()).unwrap();
            let name = resolve(&fname);
            let Some(raw) = loose_to_raw(&bytes, &name) else {
                log.push(format!("LOOSE parse fail {sub}/{fname}"));
                continue;
            };
            let label = if name == fname { fname.clone() } else { format!("{name}__{fname}") };
            let dir = out.join(sub).join(format!("{}__{}", raw.metadata().asset_type(), label));
            fs::create_dir_all(&dir).unwrap();
            write_raw(&raw, &dir);
            st.raw += 1;
            convert(&raw, &dir, &mut st, &mut log);
        }
    }

    // 3. Localised text
    for lang in fs::read_dir(root.join("loctext")).unwrap().filter_map(|e| e.ok()) {
        let ldir = out.join("loctext").join(lang.file_name());
        fs::create_dir_all(&ldir).unwrap();
        for f in fs::read_dir(lang.path()).unwrap().filter_map(|e| e.ok()) {
            let fname = f.file_name().to_string_lossy().to_string();
            let bytes = fs::read(f.path()).unwrap();
            match safe(|| LoctextResource::from_bytes(&bytes).map_err(|e| format!("{e:?}"))) {
                Ok(l) => {
                    let n = resolve(&fname);
                    let _ = fs::write(ldir.join(format!("{n}.json")), serde_json::to_vec_pretty(&l).unwrap());
                    *st.ok.entry("Loctext".into()).or_default() += 1;
                }
                Err(e) => {
                    *st.fail.entry("Loctext".into()).or_default() += 1;
                    log.push(format!("loctext {}/{fname}: {e}", lang.file_name().to_string_lossy()));
                }
            }
        }
    }

    println!("\nraw assets dumped: {}", st.raw);
    let mut k: Vec<_> = st.ok.keys().chain(st.fail.keys()).cloned().collect();
    k.sort();
    k.dedup();
    for t in k {
        println!("{t:>12}: ok {:>6}  fail {:>5}", st.ok.get(&t).unwrap_or(&0), st.fail.get(&t).unwrap_or(&0));
    }
    let _ = fs::write(out.join("_extract_errors.log"), log.join("\n"));
}
