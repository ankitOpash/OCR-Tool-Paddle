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
from PIL import Image
import io
import numpy as np
from typing import Optional,List, Dict, Union
from fastapi.responses import JSONResponse
from groq import Groq

# Assuming SYSTEM_PROMPT_CAR is properly defined in models.prompts
from models.prompts import SYSTEM_PROMPT_CAR

app = FastAPI(title="OCR API")

# Initialize OCR engines
ocr_ar = PaddleOCR(lang='ar', rec_char_type='ar', use_angle_cls=False, show_log=False)
ocr_en = PaddleOCR(lang='en', rec_char_type='en', use_angle_cls=False, show_log=False)

# Load environment variables
load_dotenv()
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

API_KEYG = os.getenv("GROQ_API_KEY")


if not API_KEYG:
    raise ValueError("Environment variable Groq is not set.")

clientG = Groq(
    # This is the default and can be omitted
    api_key=os.environ.get("API_KEYG"),
)


if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Static files setup
static_dir = "static"
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

def bytes_to_np_array(image_bytes: bytes) -> np.ndarray:
    """Convert image bytes to numpy array."""
    image = Image.open(io.BytesIO(image_bytes))
    return np.array(image)

async def process_ocr(ocr_engine: PaddleOCR, image_data: bytes) -> Optional[list]:
    """Process image with OCR engine."""
    try:
        img_array = bytes_to_np_array(image_data)
        result = await run_in_threadpool(ocr_engine.ocr, img_array, cls=True)
        return result
    except Exception as e:
        print(f"OCR processing error: {str(e)}")
        return None

def extract_with_ai(text: str, system_prompt: str) -> dict:
    """Process text with OpenAI's GPT model."""
    try:
        response = client_openai.chat.completions.create(
            model="ft:gpt-4o-mini-2024-07-18:vionex-technologies::AyH6jL2W",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            response_format={"type": "json_object"}  # Ensure JSON output
        )
        raw_response = response.choices[0].message.content
        
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            print(f"Failed to parse AI response: {raw_response}")
            return {"error": "Invalid JSON format from AI model"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")


def extract_with_groq(text: str, system_prompt: str) -> Union[str, dict]:
    try:
        # Create the messages array with system and user messages
        completion = clientG.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=1,
            max_completion_tokens=1024,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
            stop=None
        )
        
        # Ensure the response is a JSON-compatible string
        response_text = completion.choices[0].message.content
        
        if isinstance(response_text, dict):
            return json.dumps(response_text)  # Convert dict to JSON string
        return response_text
    
    except Exception as e:
        return {"error": f"Failed to extract text with Groq: {e}"}
   
# @app.post("/ocr/car")
# async def ocr_endpoint(file: UploadFile = File(...)):
#     if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
#         raise HTTPException(400, detail="Unsupported file format")
    
#     file_data = await file.read()
#     extracted_text = []

#     try:
#         if file.filename.lower().endswith('.pdf'):
#             with fitz.open(stream=file_data, filetype="pdf") as doc:
#                 for page in doc:
#                     pix = page.get_pixmap()
#                     img_bytes = pix.tobytes("png")
                    
#                     # Process with both OCR engines
#                     result_ar, result_en = await asyncio.gather(
#                         process_ocr(ocr_ar, img_bytes),
#                         process_ocr(ocr_en, img_bytes)
#                     )
                    
#                     # Extract text from results
#                     for result in [result_ar, result_en]:
#                         if result:
#                             for line in result:
#                                 if line:
#                                     for word_info in line:
#                                         if word_info and len(word_info) >= 2:
#                                             extracted_text.append(word_info[1][0])
#         else:
#             # Process image file
#             result_ar, result_en = await asyncio.gather(
#                 process_ocr(ocr_ar, file_data),
#                 process_ocr(ocr_en, file_data)
#             )
            
#             for result in [result_ar, result_en]:
#                 if result:
#                     for line in result:
#                         if line:
#                             for word_info in line:
#                                 if word_info and len(word_info) >= 2:
#                                     extracted_text.append(word_info[1][0])

#         if not extracted_text:
#             raise HTTPException(400, detail="No text extracted from document")

#         combined_text = " ".join(extracted_text)
#         ai_response = extract_with_ai(combined_text, SYSTEM_PROMPT_CAR)

#         return {
#             "status": "success",
#             "data": {
#                 "extracted_text": combined_text,
#                 "processed_data": ai_response
#             }
#         }

#     except Exception as e:
#         raise HTTPException(500, detail=f"Processing failed: {str(e)}")

@app.post("/ocr/car")
async def ocr_endpoint(files: list[UploadFile] = File(...)):
    extracted_text = []

    for file in files:
        if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            raise HTTPException(400, detail=f"Unsupported file format: {file.filename}")
        
        file_data = await file.read()

        try:
            if file.filename.lower().endswith('.pdf'):
                with fitz.open(stream=file_data, filetype="pdf") as doc:
                    for page in doc:
                        pix = page.get_pixmap()
                        img_bytes = pix.tobytes("png")
                        
                        # Process with both OCR engines
                        result_ar, result_en = await asyncio.gather(
                            process_ocr(ocr_ar, img_bytes),
                            process_ocr(ocr_en, img_bytes)
                        )
                        
                        # Extract text from results
                        for result in [result_ar, result_en]:
                            if result:
                                for line in result:
                                    if line:
                                        for word_info in line:
                                            if word_info and len(word_info) >= 2:
                                                extracted_text.append(word_info[1][0])
            else:
                # Process image file
                result_ar, result_en = await asyncio.gather(
                    process_ocr(ocr_ar, file_data),
                    process_ocr(ocr_en, file_data)
                )
                
                for result in [result_ar, result_en]:
                    if result:
                        for line in result:
                            if line:
                                for word_info in line:
                                    if word_info and len(word_info) >= 2:
                                        extracted_text.append(word_info[1][0])

        except Exception as e:
            raise HTTPException(500, detail=f"Processing failed for {file.filename}: {str(e)}")

    if not extracted_text:
        raise HTTPException(400, detail="No text extracted from documents")
    ai_response = {}
    combined_text = " ".join(extracted_text)
    raw_ai_response = extract_with_groq(combined_text, SYSTEM_PROMPT_CAR)
    ai_response["combined"] = json.loads(raw_ai_response)
    extracted_text = {
        "text": combined_text,
        "gpt_data":ai_response,
        # "side_detection": side_detections  # Uncomment if side detection is implemented
    }

    return JSONResponse(content=extracted_text)




@app.post("/ocr/cargetText")
async def ocr_endpoint(files: list[UploadFile] = File(...)):
    extracted_text = []

    for file in files:
        if not file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            raise HTTPException(400, detail=f"Unsupported file format: {file.filename}")
        
        file_data = await file.read()

        try:
            if file.filename.lower().endswith('.pdf'):
                with fitz.open(stream=file_data, filetype="pdf") as doc:
                    for page in doc:
                        pix = page.get_pixmap()
                        img_bytes = pix.tobytes("png")
                        
                        # Process with both OCR engines
                        result_ar, result_en = await asyncio.gather(
                            process_ocr(ocr_ar, img_bytes),
                            process_ocr(ocr_en, img_bytes)
                        )
                        
                        # Extract text from results
                        for result in [result_ar, result_en]:
                            if result:
                                for line in result:
                                    if line:
                                        for word_info in line:
                                            if word_info and len(word_info) >= 2:
                                                extracted_text.append(word_info[1][0])
            else:
                # Process image file
                result_ar, result_en = await asyncio.gather(
                    process_ocr(ocr_ar, file_data),
                    process_ocr(ocr_en, file_data)
                )
                
                for result in [result_ar, result_en]:
                    if result:
                        for line in result:
                            if line:
                                for word_info in line:
                                    if word_info and len(word_info) >= 2:
                                        extracted_text.append(word_info[1][0])

        except Exception as e:
            raise HTTPException(500, detail=f"Processing failed for {file.filename}: {str(e)}")

    if not extracted_text:
        raise HTTPException(400, detail="No text extracted from documents")

    # Return only the extracted text
    return JSONResponse(content={"text": " ".join(extracted_text)})






@app.get("/", tags=["Health Check"])
def health_check():
    return {"status": "active", "service": "OCR API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)