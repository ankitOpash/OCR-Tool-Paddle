python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

uvicorn app:app --reload

uvicorn app:app --reload --port 8001

//for install
pip install paddleocr