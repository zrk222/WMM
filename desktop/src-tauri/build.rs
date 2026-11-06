fn main() {
    println!("cargo:rerun-if-env-changed=WMM_NATIVE_ENGINE_SHA256");
    let sha = std::env::var("WMM_NATIVE_ENGINE_SHA256")
        .expect("Set WMM_NATIVE_ENGINE_SHA256 from the exact staged WMM engine binary");
    assert!(
        sha.len() == 64
            && sha
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "WMM_NATIVE_ENGINE_SHA256 must contain 64 lowercase hexadecimal characters"
    );
    println!("cargo:rustc-env=WMM_NATIVE_ENGINE_SHA256={sha}");
    tauri_build::build();
}
