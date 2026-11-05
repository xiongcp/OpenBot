fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "client_snapshot",
            "client_trace",
            "client_create",
            "client_start",
            "client_cancel",
            "client_preview_settings",
            "client_apply_settings",
            "client_decide",
            "client_reconnect",
        ]),
    ))
    .expect("Failed to build the fixed client command manifest");
}
