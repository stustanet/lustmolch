# Der Lustmolch
Allgemeiner container host für (semi-offizielle) Stusta websites.

## How-To
Alle management Befehle laufen entweder über `lustmolch.py` oder über `machinectl`.

### Container erstellen
```bash
python3 lustmolch.py create-container <container-name>
```
Der container wird als basic debian image in `/var/lib/machines` angelegt und `bootstrap.sh` wird ausgeführt.
Dabei werden nötige Pakete installiert, alle Konfigurationsfiles sowohl auf dem host als auch im Container abgelegt. 
Außerdem wird im container **openssh-server** installiert und gestartet. Der Port wird dynamisch auf den ersten 
freien Port ab **10022** in Inkrementen von **1000** gesetzt.

Die templates für Konfigurationsfiles liegen im directory **container**.

### Container VERNICHTEN
```bash
python3 lustmolch.py remove-container <container-name>
```
Der Container und alle Konfigurationsfiles auf dem Host werden gelöscht.

### SSH Key installieren
```bash
python3 lustmolch.py install-ssh-key <container-name> <path-to-ssh-key>
```
Der angegeben SSH key wird in `/root/.ssh/authorized_keys` kopiert. Es ist möglich den key als String-Parameter
zu übergeben, dabei muss das Flag `--key-string` gesetzt sein.