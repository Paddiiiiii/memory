//! Key storage: macOS Keychain (prod) / Windows DPAPI (dev).
#[cfg(target_os = "macos")]
pub fn platform_note() -> &'static str {
    "keychain"
}

#[cfg(target_os = "windows")]
pub fn platform_note() -> &'static str {
    "dpapi_dev"
}

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
pub fn platform_note() -> &'static str {
    "unsupported"
}
