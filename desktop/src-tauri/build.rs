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
    const DEVICE_CLIENT: &str = "WMM_GITHUB_DEVICE_CLIENT_ID";
    println!("cargo:rerun-if-env-changed={DEVICE_CLIENT}");
    let value = std::env::var_os(DEVICE_CLIENT).unwrap_or_default();
    let value = value
        .to_str()
        .expect("The public GitHub device client ID must be ASCII");
    assert!(
        value.is_empty()
            || ((10..=64).contains(&value.len())
                && value
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_')),
        "The public GitHub device client ID is invalid"
    );
    println!("cargo:rustc-env=WMM_PACKAGED_GITHUB_DEVICE_CLIENT_ID={value}");
    tauri_build::build();
}
