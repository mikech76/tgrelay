//go:build !windows

package main

func runSelftest(kind, path string, cfg *Config) {
	logf("selftest доступен только на Windows")
}
