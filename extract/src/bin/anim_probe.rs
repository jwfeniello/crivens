//! Decode every Anim asset dir given on the command line and print its basic shape.
//! usage: anim_probe <bundle_out_dir>
use std::{
    fs,
    panic::{AssertUnwindSafe, catch_unwind},
};

use bnl::{AssetMetadata, RawAsset, asset::anim::Anim};

fn main() {
    let dir = std::env::args().nth(1).unwrap();
    let (mut ok, mut fail) = (0, 0);
    let mut bone_counts = std::collections::BTreeMap::<u16, usize>::new();
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
        let r = catch_unwind(AssertUnwindSafe(|| raw.to_asset::<Anim>()));
        match r {
            Ok(Ok(a)) => {
                let d = a.asset().descriptor();
                *bone_counts.entry(d.transforms_per_keyframe()).or_default() += 1;
                let ch = a.asset().get_bone_anim_channels();
                let animated = ch.iter().filter(|c| c.rotation.is_some() || c.translation.is_some()).count();
                if ok < 6 {
                    println!(
                        "{name}: bones={} keyframes={} duration={:.3} animated_tracks={animated}",
                        d.transforms_per_keyframe(),
                        d.num_keyframes(),
                        d.duration()
                    );
                }
                ok += 1;
            }
            Ok(Err(e)) => {
                if fail < 4 {
                    println!("FAIL {name}: {e}");
                }
                fail += 1;
            }
            Err(_) => {
                if fail < 4 {
                    println!("PANIC {name}");
                }
                fail += 1;
            }
        }
    }
    println!("ok {ok} fail {fail}; track counts: {bone_counts:?}");
}
