import CoreGraphics

/// US-layout virtual key codes, so typed characters arrive as real key presses.
public enum USKeyboard {
    static let plain: [Character: CGKeyCode] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
        "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
        "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
        "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
        " ": 49, "`": 50,
    ]
    static let shifted: [Character: Character] = [
        "_": "-", "+": "=", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
        "&": "7", "*": "8", "(": "9", ")": "0", ":": ";", "\"": "'", "<": ",", ">": ".",
        "?": "/", "{": "[", "}": "]", "|": "\\", "~": "`",
    ]

    public static func keyCode(for ch: Character) -> (code: CGKeyCode, shift: Bool)? {
        if let code = plain[ch] { return (code, false) }
        if let base = shifted[ch], let code = plain[base] { return (code, true) }
        let lower = Character(ch.lowercased())
        if ch.isUppercase, let code = plain[lower] { return (code, true) }
        return nil
    }
}
