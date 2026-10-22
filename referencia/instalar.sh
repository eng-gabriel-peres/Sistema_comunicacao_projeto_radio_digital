
#!/usr/bin/env bash
set -Eeuo pipefail

# Diretório do projeto e ambiente virtual
PROJECT_DIR="${HOME}/rtl-sdr-python"
VENV_DIR="${PROJECT_DIR}/venv"

echo "=== Instalação do ambiente Python para RTL-SDR ==="

# Verifica se o sistema é Fedora
if [[ ! -r /etc/fedora-release ]]; then
    echo "Erro: este script foi preparado para o Fedora Linux."
    exit 1
fi

# Instala dependências nativas do sistema
echo "[1/5] Instalando dependências do sistema..."

# Cria o diretório do projeto
echo "[2/5] Preparando diretório do projeto..."
mkdir -p "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

# Cria o ambiente virtual, se necessário
echo "[3/5] Criando ambiente virtual..."
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
fi

# Ativa o ambiente virtual
source "${VENV_DIR}/bin/activate"

# Atualiza as ferramentas de instalação
python -m pip install --upgrade pip setuptools wheel

# Instala bibliotecas Python para SDR e processamento de sinais
echo "[4/5] Instalando bibliotecas Python..."
python -m pip install --upgrade \
    "pyrtlsdr[lib]" \
    numpy \
    scipy \
    matplotlib \
    scipy

# Registra as dependências instaladas
python -m pip freeze > requirements.txt

echo "[5/5] Verificando instalação..."
python -c "import numpy, scipy; from rtlsdr import RtlSdr; print('Bibliotecas Python carregadas com sucesso.')"

echo
echo "Instalação concluída!"
echo "Projeto: ${PROJECT_DIR}"
echo "Ambiente virtual: ${VENV_DIR}"
echo
echo "Para ativar o ambiente:"
echo "source '${VENV_DIR}/bin/activate'"
echo
echo "Para testar o receptor:"
echo "rtl_test -t"
