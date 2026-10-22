# Ambiente de desenvolvimento

Tudo o que o projeto precisa para desenvolver, simular e operar os rádios.
Depois de cada passo, conferir com `python scripts/verificar_ambiente.py`.

## Versões fixadas

| Componente | Versão | Por quê |
|---|---|---|
| Python | 3.13 (mínimo 3.11, por causa do tomllib) | Já instalado no PC de desenvolvimento |
| libiio (biblioteca C) | **0.25** | O pyadi-iio usa a API 0.x; a libiio 1.0 mudou a API |
| pylibiio | 0.25 | Precisa casar com a libiio do sistema |
| pyadi-iio | 0.0.21 | Controle do Pluto |
| pyrtlsdr + pyrtlsdrlib | 0.5.1 + 0.0.7 | Controle do RTL; o pyrtlsdrlib traz a librtlsdr pronta |
| numpy, scipy, matplotlib | ver `requirements.txt` | |
| ruff, mypy, pytest, pytest-cov | ver `requirements-dev.txt` | Portão de qualidade |
| PyQt5 | 5.15.11 | O `referencia/teste_FM.py` força o backend gráfico `Qt5Agg` |

## Windows

### 1. Ambiente Python (sem permissão de administrador)

Na raiz do repositório:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install -e .
git config core.hooksPath .githooks
```

### 2. Instaladores do sistema (pedem permissão de administrador)

Os três instaladores oficiais ficam em `Trabalho_SiSCOM/instaladores/` (fora do repositório). Todos foram baixados dos releases oficiais no GitHub e têm assinatura digital válida:

| Arquivo | Origem | Assinatura | SHA-256 |
|---|---|---|---|
| `libiio-0.25.gb6028fd-setup.exe` | github.com/analogdevicesinc/libiio, release v0.25 | Analog Devices | `5bf4c600d5c65d4061348c1f9576c2d39203729120b268bdea4f3ba05d688e7c` |
| `PlutoSDR-M2k-USB-Drivers.exe` | github.com/analogdevicesinc/plutosdr-m2k-drivers-win, release v0.9 | Analog Devices | `c53dac79be6af8e268b2b5460856d46501f3a61c7b820cbfc3fe24288960550d` |
| `zadig-2.9.exe` | github.com/pbatard/libwdi, release v1.5.1 | Akeo Consulting | `4ecaa95df3da3621486a043aef8b3050b8bafe7c901402871e816229ef82039b` |

**a) libiio (para o Pluto):** executar `libiio-0.25.gb6028fd-setup.exe` e aceitar as opções padrão. Ele coloca a `libiio.dll` e as ferramentas `iio_info` no sistema.

**b) Drivers USB do Pluto:** executar `PlutoSDR-M2k-USB-Drivers.exe`. Depois, ao conectar o Pluto, ele aparece como unidade de disco e como rede USB (`192.168.2.1`).

**c) Driver WinUSB do RTL-SDR (Zadig):** sem isso o Windows usa o driver de TV digital e o rádio não abre.

1. Conectar o RTL-SDR.
2. Executar `zadig-2.9.exe` e aceitar o pedido de administrador.
3. Menu **Options → List All Devices**.
4. Escolher **Bulk-In, Interface (Interface 0)**. Confirmar que o USB ID é `0BDA 2838`. Não escolher a Interface 1.
5. No campo do driver de destino, deixar **WinUSB** e clicar em **Replace Driver** (ou Install Driver).
6. Desconectar e conectar o RTL-SDR de novo.

O Zadig grava o driver para aquela porta USB. Se o RTL for ligado em outra porta e não abrir, repetir o processo.

### 3. Conferir

```powershell
.venv\Scripts\python scripts\verificar_ambiente.py
```

Todas as linhas devem aparecer como `OK`. O Pluto só aparece como `OK` quando está conectado.

## Fedora (computadores da bancada)

O `referencia/instalar.sh` do professor prepara o RTL-SDR no Fedora, mas não instala nada para o Pluto e cria o ambiente em `~/rtl-sdr-python`, fora do repositório. Para rodar **este** projeto no Fedora:

```bash
sudo dnf install -y python3 python3-pip git libiio rtl-sdr
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
sudo modprobe -r dvb_usb_rtl28xxu
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .
git config core.hooksPath .githooks
.venv/bin/python scripts/verificar_ambiente.py
```

O pacote `rtl-sdr` do dnf instala as regras de udev que deixam usar o dongle sem `sudo`. A linha do `blacklist` impede que o kernel ligue o dongle ao driver de TV digital. Se a libiio do Fedora não for da série 0.x, avisar antes de instalar outra versão.

## Firmware

Não há firmware para compilar. O Pluto usa o firmware da Analog Devices (conferir a versão com `iio_info -s` ou abrindo `info.html` na unidade do Pluto) e o RTL-SDR não tem firmware.
