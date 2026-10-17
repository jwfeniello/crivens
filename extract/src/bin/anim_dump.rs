//! Decode every Anim asset in an extracted bundle dir and write anim.json next to it.
//! usage: anim_dump <bundle_out_dir>
use std::{
    fs,
    panic::{AssertUnwindSafe, catch_unwind},
};

use bnl::{AssetMetadata, RawAsset, asset::anim::Anim};
use serde_json::json;

fn main() {
    let dir = std::env::args().nth(1).unwrap();
    let (mut ok, mut fail) = (0, 0);
    for e in fs::read_dir(&dir).unwrap().filter_map(|e| e.ok()) {
        let name = e.file_name().to_string_lossy().to_string();
        if !name.starts_with("Anim__") {
            continue;
        }
        let p = e.path();
        let meta = AssetMetadata::from_bytes(&fs::read(p.join("metadata")).unwrap()).unwrap();
        let desc = fs::read(p.join("descriptor")).unwrap();
        let res: Vec<Vec<u8>> = (0..)
            .map_while(|i| fs::read(p.join(format!("resource{i}"))).ok())
            .collect();
        let raw = RawAsset::new(meta, desc, (!res.is_empty()).then_some(res));
        match catch_unwind(AssertUnwindSafe(|| raw.to_asset::<Anim>())) {
            Ok(Ok(a)) => {
                let d = a.asset().descriptor();
                let tracks: Vec<_> = a
                    .asset()
                    .get_bone_anim_channels()
                    .into_iter()
                    .map(|c| json!({"rotation": c.rotation, "translation": c.translation, "scale": c.scale}))
                    .collect();
                let out = json!({
                    "name": name.trim_start_matches("Anim__"),
                    "duration": d.duration(),
                    "inverse_divisor": d.inverse_divisor(),
                    "num_keyframes": d.num_keyframes(),
                    "num_tracks": d.transforms_per_keyframe(),
                    "tracks": tracks,
                });
                fs::write(p.join("anim.json"), serde_json::to_vec(&out).unwrap()).unwrap();
                ok += 1;
            }
            Ok(Err(e)) => {
                eprintln!("FAIL {name}: {e}");
                fail += 1;
            }
            Err(_) => {
                eprintln!("PANIC {name}");
                fail += 1;
            }
        }
    }
    println!("ok {ok} fail {fail}");
}
