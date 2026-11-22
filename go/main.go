package main

import (
	"os"
	"path/filepath"
)

func main() {
	args := os.Args[1:]
	configPath := ""
	headless := false
	var rest []string

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--config", "-config", "-c":
			if i+1 < len(args) {
				configPath = args[i+1]
				i++
			}
		case "--headless", "-headless":
			headless = true
		default:
			rest = append(rest, args[i])
		}
	}

	if runCLI(rest, configPath) {
		return
	}
	runServer(configPath, headless)
}

func runServer(configPath string, headless bool) {
	path := configPath
	if path == "" {
		path = findConfig()
	}
	createdPath, created := ensureConfig(path)
	if created {
		showFirstRun(createdPath)
		return
	}
	path = createdPath

	// При перезапуске из меню предыдущая копия ещё держит порты. Ждём её
	// завершения до того, как открывать свои, иначе новый экземпляр падает
	// с «address already in use», а старый уже вышел.
	if !takeOver(headless) {
		return
	}

	initLog(filepath.Join(filepath.Dir(path), "tgrelay.log"))

	app, err := NewApp(path)
	if err != nil {
		logf("ошибка конфига: %v", err)
		showError(err.Error())
		os.Exit(1)
	}
	appInstance = app

	if err := app.Start(); err != nil {
		logf("ошибка запуска: %v", err)
		showError(err.Error())
		os.Exit(1)
	}
	defer app.Stop()

	logf("конфиг: %s", path)
	logf("tgrelay %s — MTProto + SOCKS5", version)
	logf("прокси: %d", len(app.Cfg.Proxies))
	for _, pr := range app.Pool.proxies {
		logf("  %s (%s)", pr.Addr(), kindOrAuto(pr.Kind()))
	}
	logf("секретов MTProto: %d, пользователей SOCKS5: %d",
		len(app.Cfg.Secrets), len(app.Cfg.Users))

	runUI(app, headless)
}