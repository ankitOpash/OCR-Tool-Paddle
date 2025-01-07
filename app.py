from fastapi import FastAPI, File, UploadFile
from typing import List, Dict, Union
import pymupdf
from paddleocr import PaddleOCR
import fitz  
import os
import uvicorn
from dotenv import load_dotenv
from openai import OpenAI

app = FastAPI(title="OCR  API")

# Initialize the OCR model
ocr = PaddleOCR(lang='ar')

load_dotenv()
client = OpenAI()
# client = OpenAI()

API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise ValueError("Environment variable OPENAI_API_KEY is not set.")


def extract_with_ai(text: str) -> Dict[str, Dict[str, str]]:
    prompt = """
    You are an advanced OCR extraction agent. Your task is to extract all identifiable key-value pairs from the provided text. 

    1. Identify all fields dynamically — do not assume predefined fields.
    2. Return results in a JSON format where:
       - The key is the field name (in English if possible).
       - The value contains both English and Arabic (if both are available).
       - If only one language is present, return that.
    3. Avoid extra text, summaries, or explanations. Only return a clean JSON Format with key-value pairs strict to the requirements.

    Example output:
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

    Text to process:
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content

@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    # Save the uploaded file
    os.makedirs('uploads', exist_ok=True)
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    extracted_text = []

    if file.filename.lower().endswith('.pdf'):
        # Open the PDF file
        pdf_document = fitz.open(file_path)
        for page_number in range(len(pdf_document)):
            # Get the page
            page = pdf_document.load_page(page_number)
            # Render the page to an image
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
                
        
            
        
        # return {"status": "success", "data": extracted_data}
        
    # Return the extracted text as JSON
    extracted_text = " ".join(extracted_text) 
    ai_response = extract_with_ai(extracted_text)
    print("fdfdfdfdf",ai_response)
    extracted_text= {
                "text": extracted_text,
                "gpt_data": ai_response
            }
    return {"status": "success", "data": extracted_text}

@app.get("/")
def read_root():
    return {"message": "OCR Tool API"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)