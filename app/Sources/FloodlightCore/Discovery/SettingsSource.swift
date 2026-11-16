/// The top-level System Settings panes for macOS 26, with the identifiers from System Settings'
/// own Sidebar.plist. Opened through the x-apple.systempreferences URL scheme.
public enum SettingsSource {
    static let panes: [(title: String, id: String, keywords: [String])] = [
        ("Wi\u{2011}Fi", "com.apple.wifi-settings-extension", ["wifi", "wireless", "internet"]),
        ("Bluetooth", "com.apple.BluetoothSettings", []),
        ("Network", "com.apple.Network-Settings.extension", ["ethernet", "vpn", "firewall"]),
        ("Energy", "com.apple.Battery-Settings.extension", ["battery", "power", "sleep"]),
        ("General", "com.apple.systempreferences.GeneralSettings", ["about", "software update", "storage"]),
        ("Accessibility", "com.apple.Accessibility-Settings.extension", ["voiceover", "zoom"]),
        ("Appearance", "com.apple.Appearance-Settings.extension", ["dark mode", "light mode", "accent colour"]),
        ("Desktop & Dock", "com.apple.Desktop-Settings.extension", ["dock", "mission control", "hot corners"]),
        ("Displays", "com.apple.Displays-Settings.extension", ["display", "monitor", "resolution", "night shift"]),
        ("Menu Bar", "com.apple.ControlCenter-Settings.extension", ["control center", "control centre"]),
        ("Siri", "com.apple.Siri-Settings.extension", ["apple intelligence"]),
        ("Spotlight", "com.apple.Spotlight-Settings.extension", []),
        ("Wallpaper", "com.apple.Wallpaper-Settings.extension", ["background"]),
        ("Notifications", "com.apple.Notifications-Settings.extension", []),
        ("Sound", "com.apple.Sound-Settings.extension", ["volume", "audio", "output", "input"]),
        ("Focus", "com.apple.Focus-Settings.extension", ["do not disturb"]),
        ("Screen Time", "com.apple.Screen-Time-Settings.extension", []),
        ("Lock Screen", "com.apple.Lock-Screen-Settings.extension", ["screen saver"]),
        ("Privacy & Security", "com.apple.settings.PrivacySecurity.extension", ["permissions", "filevault"]),
        ("Login Password", "com.apple.Touch-ID-Settings.extension", ["touch id", "password"]),
        ("Users & Groups", "com.apple.Users-Groups-Settings.extension", ["accounts"]),
        ("Internet Accounts", "com.apple.Internet-Accounts-Settings.extension", ["email accounts"]),
        ("Game Center", "com.apple.Game-Center-Settings.extension", []),
        ("iCloud", "com.apple.systempreferences.AppleIDSettings", ["apple account", "apple id"]),
        ("Wallet & Apple\u{00A0}Pay", "com.apple.WalletSettingsExtension", []),
        ("Keyboard", "com.apple.Keyboard-Settings.extension", ["shortcuts", "input sources"]),
        ("Mouse", "com.apple.Mouse-Settings.extension", ["scrolling"]),
        ("Printers & Scanners", "com.apple.Print-Scanner-Settings.extension", ["printer", "scanner"]),
    ]

    public static func items() -> [Item] {
        panes.map {
            Item(id: "settings:\($0.id)", title: $0.title, kind: .settingsPane,
                 path: "x-apple.systempreferences:\($0.id)", keywords: $0.keywords)
        }
    }
}
