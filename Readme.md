python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

uvicorn app:app --reload

pip install paddlepaddle