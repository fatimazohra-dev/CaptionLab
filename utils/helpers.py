import ssl
import nltk
import os

def fix_ssl():
    """Fix SSL certificate verification issues"""
    ssl._create_default_https_context = ssl._create_unverified_context

def ensure_nltk_data_basic():
    """Ensure basic NLTK data is downloaded"""
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)

def format_srt_timestamp(seconds_float):
    """Convert seconds to SRT timestamp format"""
    hours = int(seconds_float // 3600)
    minutes = int((seconds_float % 3600) // 60)
    seconds = int(seconds_float % 60)
    milliseconds = int((seconds_float % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def create_temp_srt_file(segments, output_path):
    """Create a temporary SRT file from segments"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            start_time = format_srt_timestamp(segment['start'])
            end_time = format_srt_timestamp(segment['end'])
            text = segment['text'].strip()
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n") 