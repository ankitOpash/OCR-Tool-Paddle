from fastapi import FastAPI, File, UploadFile, HTTPException
import fitz
from paddleocr import PaddleOCR
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
from dotenv import load_dotenv
import json
import asyncio
from fastapi.concurrency import run_in_threadpool
from openai import OpenAI
from models.prompts import (
    SYSTEM_PROMPT_INTRO,
    SYSTEM_PROMPT_VEHICLE_REGISTRATION,
    SYSTEM_PROMPT_DEFAULT,
    SYSTEM_PROMPT_CAR,
    SYSTEM_PROMPT_DRIVING_LICENSE,
    SYSTEM_PROMPT_EMIRATES_CARD,
)

app = FastAPI(title="OCR API")

# Create two OCR instances:
# One configured for Arabic and the other for English.
ocr_ar = PaddleOCR(lang='ar', rec_char_type='ar', use_angle_cls=True, show_log=False)
ocr_en = PaddleOCR(lang='en', rec_char_type='en', use_angle_cls=True, show_log=False)

# Load environment variables
load_dotenv()
clientOpen = OpenAI()
API_KEY = os.getenv("OPENAI_API_KEY")
APY_KEY_CLOUDE = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("Environment variable OPENAI_API_KEY is not set.")

# Ensure the static directory exists
static_dir = "static"
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

def extract_with_ai(text: str, system_prompt: str, sample: dict = None) -> dict:
    try:
        sample_json = json.dumps(sample) if sample is not None else None
        response = clientOpen.chat.completions.create(
            model="ft:gpt-4o-mini-2024-07-18:vionex-technologies::AyH6jL2W",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            prediction={"type": "content", "content": sample_json} if sample_json else None
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")

@app.post("/ocr/car")
async def ocr_endpoint(file: UploadFile = File(...)):
    """
    Process an uploaded file (PDF or image) by running it through both
    the Arabic and English OCR engines concurrently, then merging the results.
    """
    if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    file_data = await file.read()
    extracted_text = []

    if file.filename.lower().endswith('.pdf'):
        try:
            with fitz.open(stream=file_data, filetype="pdf") as pdf_document:
                tasks = []
                for page in pdf_document:
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    # Process each page with both OCR models concurrently.
                    task_ar = run_in_threadpool(ocr_ar.ocr, img_data)
                    task_en = run_in_threadpool(ocr_en.ocr, img_data)
                    tasks.append(asyncio.gather(task_ar, task_en))
                results = await asyncio.gather(*tasks)
                for result_pair in results:
                    result_ar, result_en = result_pair
                    # Extract words from both OCR results.
                    words_ar = [word_info[1][0] for line in result_ar for word_info in line]
                    words_en = [word_info[1][0] for line in result_en for word_info in line]
                    extracted_text.extend(words_ar)
                    extracted_text.extend(words_en)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF processing failed: {str(e)}")
    else:
        try:
            result_ar, result_en = await asyncio.gather(
                run_in_threadpool(ocr_ar.ocr, file_data),
                run_in_threadpool(ocr_en.ocr, file_data)
            )
            words_ar = [word_info[1][0] for line in result_ar for word_info in line]
            words_en = [word_info[1][0] for line in result_en for word_info in line]
            extracted_text.extend(words_ar)
            extracted_text.extend(words_en)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
    
    combined_text = " ".join(extracted_text)

    # Process the combined extracted text with the AI model.
    try:
        raw_ai_response = extract_with_ai(combined_text, SYSTEM_PROMPT_CAR)
        ai_response = json.loads(raw_ai_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")
    
    return {"status": "success", "data": {"text": combined_text, "gpt_data": ai_response}}

@app.get("/", tags=["Health"])
def read_root():
    return {"message": "OCR Tool API is running"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
