# 📊 Dashboard de Análise Diária — BLiP Analytics

Um dashboard interativo construído com **Streamlit** para análise de **usuários únicos** em bots da plataforma **BLiP**, com base no primeiro contato do período analisado.  
O sistema coleta eventos via API do BLiP, processa e apresenta visualizações por **horário comercial**, **semana ISO**, **dia da semana** e **hora do dia**, além de permitir **exportação de relatórios PDF**.

---

## 🚀 Funcionalidades
- **Coleta automática** de eventos de um bloco/ação específico do bot no BLiP.
- Filtros por:
  - Últimos N dias
  - Intervalo de datas personalizado
  - Fuso horário de análise
  - Horário comercial (início e fim configuráveis)
- Visualizações:
  - Distribuição **dentro x fora** do horário comercial
  - Evolução por semana ISO
  - Distribuição por dia da semana
  - Distribuição por hora do dia
- **Exportação de relatório PDF** com gráficos e resumo executivo.
- **Visualização de dados brutos** (até 5.000 linhas).
- Interface simples, intuitiva e responsiva.

---

## 📦 Instalação

### 1️⃣ Clone este repositório
```bash
git clone https://github.com/DellaSerraaaSource/dash-analise-diaria.git
cd dash-analise-diaria
```

### 2️⃣ Crie um ambiente virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3️⃣ Instale as dependências
```bash
pip install -r requirements.txt
```

---

## ▶️ Execução
Inicie o servidor local do Streamlit:
```bash
streamlit run app.py
```
Acesse no navegador:  
```
http://localhost:8501
```

---

## 🔑 Credenciais
O sistema solicita a **BLiP API Key** na própria interface, garantindo que:
- A chave **não é salva** permanentemente
- É usada apenas na sessão ativa
- Compatível com tokens temporários

---

## 🗂 Estrutura do projeto
```
dash-analise-diaria/
│
├── app.py               # Aplicação principal em Streamlit
├── requirements.txt     # Lista de dependências
├── .gitignore           # Arquivos ignorados pelo Git
└── README.md            # Este arquivo
```

---

## 📸 Prints
*(adicione imagens depois que rodar o app)*

---

## 📜 Licença
Este projeto é distribuído sob a licença **MIT**.  
Você é livre para usar, modificar e distribuir, desde que mantenha os créditos originais.

---

## 🤝 Contribuindo
Pull Requests são bem-vindos!  
Siga as boas práticas de **Clean Code** e **PEP8** para manter o projeto organizado.

---

**Desenvolvido por [Higor Della Serra](https://github.com/DellaSerraaaSource)** 💡
