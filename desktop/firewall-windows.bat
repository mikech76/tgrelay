@echo off
netsh advfirewall firewall add rule name="MTProxy 55055" dir=in action=allow protocol=TCP localport=55055
netsh advfirewall firewall add rule name="SOCKS 55056" dir=in action=allow protocol=TCP localport=55056
netsh advfirewall firewall add rule name="WireGuard 51820" dir=in action=allow protocol=UDP localport=51820
echo Rules added. Press any key...
pause
