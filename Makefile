.PHONY: setup setup-gpu serve demo doctor test tools

setup:            ## core deps (board, pipelines, QA, motion engine) — works without a GPU
	pip install -r requirements.txt
	playwright install chromium

setup-gpu:        ## local model stack (Qwen / H3 / VoxCPM2 / ACE-Step / Foley / SFX)
	bash scripts/install_models.sh

serve:            ## storyboard board on http://127.0.0.1:7788
	python -m midea serve

demo:             ## end-to-end run without GPU models
	python -m midea --mock make "製作一支 30 秒解釋神經網路的動畫" --duration 30 -y

doctor:
	python -m midea doctor

tools:
	python -m midea tools

test:
	MIDEA_MODE=mock python -m pytest -q tests
