//go:build windows

package main

// systemLang — язык интерфейса Windows (русская система → ru, иначе en).
func systemLang() string {
	id, _, _ := pGetUserDefaultUILanguage.Call()
	if uint32(id)&0x3FF == 0x19 { // LANG_RUSSIAN
		return "ru"
	}
	return "en"
}
