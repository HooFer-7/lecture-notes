import google.generativeai as genai
import json
import re
import asyncio
from functools import partial
from typing import Dict, Any
from app.config import settings

class GeminiService:
    """AI Summarization using Google Gemini"""
    
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('models/gemini-flash-latest')
    
    async def generate_notes(self, transcript: str) -> Dict[str, Any]:
        """Generate structured notes from transcript (async wrapper)"""
        # Run the sync Gemini API call in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(self._generate_notes_sync, transcript)
        )
        return result
    
    def _generate_notes_sync(self, transcript: str) -> Dict[str, Any]:
        """Synchronous note generation"""
        
        # Validate transcript
        if not transcript or len(transcript.strip()) < 50:
            raise ValueError("Transcript is too short or empty")
        
        # Truncate very long transcripts to avoid token limits
        max_chars = 30000  # Approx 7500 tokens
        if len(transcript) > max_chars:
            print(f"⚠️ Transcript truncated from {len(transcript)} to {max_chars} chars")
            transcript = transcript[:max_chars] + "\n\n[Transcript truncated due to length]"
        
        prompt = self._create_prompt(transcript)
        
        try:
            print("🤖 Generating structured notes with Gemini...")
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                    top_p=0.8,
                    top_k=40
                ),
                safety_settings=[
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]
            )
            
            # Extract and parse JSON
            notes = self._extract_json_from_response(response.text)
            
            # Validate structure
            notes = self._validate_notes_structure(notes)
            
            print("✅ Notes generated successfully!")
            return notes
            
        except Exception as e:
            print(f"❌ Error generating notes: {e}")
            # Return fallback structure
            return self._create_fallback_notes(transcript, str(e))
    
    def _create_prompt(self, transcript: str) -> str:
        """Create the prompt for Gemini"""
        return f"""You are an expert educational note-taker. Analyze this lecture transcript and create comprehensive, well-structured notes.

TRANSCRIPT:
{transcript}

Create structured notes in this EXACT JSON format (return ONLY valid JSON, no markdown, no explanations):

{{
    "title": "A clear, descriptive title for the lecture",
    "summary": "A 2-3 sentence summary of the main topic and key takeaways",
    "sections": [
        {{
            "heading": "Section 1 Title",
            "content": "Detailed explanation in 2-3 paragraphs covering this topic",
            "bullet_points": [
                "Key point 1 with specific details",
                "Key point 2 with specific details",
                "Key point 3 with specific details"
            ],
            "timestamp": "Optional: e.g., '5:30' or 'Beginning' or null"
        }}
    ],
    "key_terms": [
        "Important term 1",
        "Important term 2",
        "Important term 3"
    ],
    "formulas": [
        "Mathematical formula 1 (use LaTeX notation if applicable)",
        "Mathematical formula 2"
    ],
    "action_items": [
        "Homework assignment mentioned",
        "Topic to review before next class",
        "Additional reading suggested"
    ],
    "questions": [
        "Important question 1 raised during lecture",
        "Important question 2 for review"
    ]
}}

GUIDELINES:
- Create 3-6 logical sections based on natural topic transitions
- Each section should have 3-5 detailed bullet points
- Extract 5-15 key terms (important vocabulary, concepts, names)
- Include formulas/equations if any are discussed
- Note any homework, assignments, or action items mentioned
- List important questions raised (not just rhetorical ones)
- Use empty arrays [] if a category doesn't apply
- Be comprehensive but concise
- Use clear, academic language
- Ensure all JSON is properly formatted with correct quotes and commas

CRITICAL: Return ONLY the JSON object. No markdown code blocks, no explanations, no additional text."""
    
    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """Extract and parse JSON from Gemini response"""
        response_text = response_text.strip()
        
        # Remove markdown code blocks
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
        response_text = response_text.strip()
        
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            print(f"Response preview: {response_text[:500]}")
            raise
    
    def _validate_notes_structure(self, notes: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fix notes structure"""
        required_keys = {
            "title": "Untitled Lecture",
            "summary": "Summary unavailable",
            "sections": [],
            "key_terms": [],
            "formulas": [],
            "action_items": [],
            "questions": []
        }
        
        # Ensure all required keys exist
        for key, default in required_keys.items():
            if key not in notes or notes[key] is None:
                notes[key] = default
        
        # Validate sections structure
        if notes["sections"]:
            for section in notes["sections"]:
                if "heading" not in section:
                    section["heading"] = "Untitled Section"
                if "content" not in section:
                    section["content"] = ""
                if "bullet_points" not in section:
                    section["bullet_points"] = []
                if "timestamp" not in section:
                    section["timestamp"] = None
        else:
            # Create at least one section from summary
            notes["sections"] = [{
                "heading": "Overview",
                "content": notes["summary"],
                "bullet_points": ["See transcript for full details"],
                "timestamp": None
            }]
        
        return notes
    
    def _create_fallback_notes(self, transcript: str, error_msg: str) -> Dict[str, Any]:
        """Create fallback notes when generation fails"""
        print(f"⚠️ Using fallback notes structure due to: {error_msg}")
        
        # Create basic notes from transcript
        words = transcript.split()
        preview = ' '.join(words[:100]) + "..." if len(words) > 100 else transcript
        
        return {
            "title": "Lecture Notes (Auto-generated)",
            "summary": f"Automatic transcription available. Manual review recommended. Error: {error_msg[:100]}",
            "sections": [{
                "heading": "Transcript Preview",
                "content": preview,
                "bullet_points": [
                    "Full transcript available",
                    "AI note generation encountered an error",
                    "Please review the raw transcript"
                ],
                "timestamp": None
            }],
            "key_terms": [],
            "formulas": [],
            "action_items": ["Review full transcript manually"],
            "questions": []
        }

# Initialize service
gemini_service = GeminiService()