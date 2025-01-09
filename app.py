from fastapi import FastAPI, File, UploadFile, HTTPException
from typing import List
import fitz
from paddleocr import PaddleOCR
import os
import httpx
import uvicorn
from dotenv import load_dotenv
import json
from pydantic import BaseModel

app = FastAPI(title="OCR API")

# Initialize the OCR model
ocr = PaddleOCR(lang='ar')

# Load environment variables
load_dotenv()

OLLAMA_URL = "http://213.173.108.12:17413"  # Your Ollama API URL
MODEL_NAME = "llama3.2"  # Base model name
SYSTEM_PROMPT = """You are an advanced OCR extraction agent. Your task is to extract all identifiable key-value pairs from the provided text.

1. Dynamically identify all fields — do not assume predefined fields.
2. Return results in a strict JSON format where:
   - The key is the field name (in English, if possible).
   - The value includes both English and Arabic translations, if available.
   - If only one language is present, include only that language.
3. Avoid any extra text, summaries, or explanations. Only return a clean JSON object adhering strictly to these requirements.

Output Format Example:
{
    "Field Name 1": {
        "English": "Value in English",
        "Arabic": "Value in Arabic (if available)"
    },
    "Field Name 2": {
        "English": "Value in English",
        "Arabic": "Value in Arabic (if available)"
    }
}

Rules:
- Clean OCR artifacts (e.g., replace '0' with 'O', and 'l' with '1', where applicable).
- Format dates in the "DD-MMM-YY" format (e.g., 01-Jan-25).
- Include all fields, even if some values are empty.
- Return ONLY the JSON object, with no additional text or formatting."""


async def extract_with_ai(extracted_text: str) -> dict:
    """Call the Ollama API with the extracted text."""
    ollama_request = {
        "model": MODEL_NAME,
        "prompt": extracted_text,
        "system": SYSTEM_PROMPT,
        "stream": False
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=ollama_request,
                timeout=30.0
            )
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Error from Ollama API")
            
            ollama_response = response.json()
            response_text = ollama_response.get("response", "")
            
            # Parse JSON from the response
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0]
            else:
                json_text = response_text.strip()
            
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse JSON: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    # Save the uploaded file
    os.makedirs('uploads', exist_ok=True)
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    extracted_text = []

    if file.filename.lower().endswith('.pdf'):
        # Process each page in the PDF
        pdf_document = fitz.open(file_path)
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            pix = page.get_pixmap()
            img_path = os.path.join('uploads', f"{file.filename}_page_{page_number}.png")
            pix.save(img_path)

            # Perform OCR on the image
            result = ocr.ocr(img_path)
            for line in result:
                for word_info in line:
                    extracted_text.append(word_info[1][0])
    else:
        # Perform OCR on the image file
        result = ocr.ocr(file_path)
        for line in result:
            for word_info in line:
                extracted_text.append(word_info[1][0])

    # Combine the extracted text
    extracted_text = " ".join(extracted_text)

    # Use AI to process extracted text
    try:
        ai_response = await extract_with_ai(extracted_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")

    # Combine the results
    return {
        "status": "success",
        "data": {
            "text": extracted_text,
            "gpt_data": ai_response
        }
    }


@app.get("/")
def read_root():
    return {"message": "OCR Tool API"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
