//go:build windows

package main

import (
	"bytes"
	"embed"
	"image"
	"image/png"
	"sync"
	"unsafe"
)

//go:embed assets/*.png
var assetFS embed.FS

var (
	assetMu    sync.Mutex
	assetCache = map[string]uintptr{}
	iconCache  = map[string]uintptr{}
)

func loadPNG(name string) image.Image {
	data, err := assetFS.ReadFile("assets/" + name + ".png")
	if err != nil {
		return image.NewRGBA(image.Rect(0, 0, 16, 16))
	}
	img, err := png.Decode(bytes.NewReader(data))
	if err != nil {
		return image.NewRGBA(image.Rect(0, 0, 16, 16))
	}
	return img
}

// hbitmapFromImage — 32-битный DIB с premultiplied alpha для пунктов меню.
func hbitmapFromImage(img image.Image) uintptr {
	bounds := img.Bounds()
	w, h := bounds.Dx(), bounds.Dy()

	bmi := bitmapInfo{}
	bmi.bmiHeader.biSize = uint32(unsafe.Sizeof(bmi.bmiHeader))
	bmi.bmiHeader.biWidth = int32(w)
	bmi.bmiHeader.biHeight = -int32(h) // top-down
	bmi.bmiHeader.biPlanes = 1
	bmi.bmiHeader.biBitCount = 32
	bmi.bmiHeader.biCompression = 0 // BI_RGB

	var bits unsafe.Pointer
	hbm, _, _ := pCreateDIBSection.Call(0,
		uintptr(unsafe.Pointer(&bmi)), 0,
		uintptr(unsafe.Pointer(&bits)), 0, 0)
	if hbm == 0 || bits == nil {
		return 0
	}

	buf := unsafe.Slice((*byte)(bits), w*h*4)
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			r, g, b, a := img.At(bounds.Min.X+x, bounds.Min.Y+y).RGBA()
			r8, g8, b8, a8 := uint8(r>>8), uint8(g>>8), uint8(b>>8), uint8(a>>8)
			// premultiplied
			i := (y*w + x) * 4
			buf[i+0] = uint8(uint32(b8) * uint32(a8) / 255)
			buf[i+1] = uint8(uint32(g8) * uint32(a8) / 255)
			buf[i+2] = uint8(uint32(r8) * uint32(a8) / 255)
			buf[i+3] = a8
		}
	}
	return hbm
}

func hiconFromImage(img image.Image) uintptr {
	hbm := hbitmapFromImage(img)
	if hbm == 0 {
		return 0
	}
	bounds := img.Bounds()
	mask, _, _ := pCreateBitmap.Call(uintptr(bounds.Dx()), uintptr(bounds.Dy()), 1, 1, 0)
	info := iconInfo{fIcon: 1, hbmMask: mask, hbmColor: hbm}
	icon, _, _ := pCreateIconIndirect.Call(uintptr(unsafe.Pointer(&info)))
	pDeleteObject.Call(mask)
	pDeleteObject.Call(hbm)
	return icon
}

func menuBitmap(name string) uintptr {
	assetMu.Lock()
	defer assetMu.Unlock()
	if hbm, ok := assetCache[name]; ok {
		return hbm
	}
	hbm := hbitmapFromImage(loadPNG("menu_" + name))
	assetCache[name] = hbm
	return hbm
}

func trayIcon(state string) uintptr {
	assetMu.Lock()
	defer assetMu.Unlock()
	if icon, ok := iconCache[state]; ok {
		return icon
	}
	icon := hiconFromImage(loadPNG("icon_" + state))
	iconCache[state] = icon
	return icon
}
