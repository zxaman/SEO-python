from flask import Flask, render_template_string, request, jsonify, flash
from bs4 import BeautifulSoup
import requests
import re
from urllib.parse import urlparse
import time
import ssl
import socket
import whois
import json
from datetime import datetime
import validators
import xml.etree.ElementTree as ET
import logging
import requests_cache
import os
from dotenv import load_dotenv
import hashlib
from functools import lru_cache

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='seo_analyzer.log'
)
logger = logging.getLogger(__name__)

# Initialize cache
requests_cache.install_cache('seo_cache', expire_after=3600)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Cache for storing analysis results
analysis_cache = {}

@lru_cache(maxsize=100)
def get_cached_analysis(url):
    """Get cached analysis results for a URL."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    return analysis_cache.get(cache_key)

def cache_analysis(url, results):
    """Cache analysis results for a URL."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    analysis_cache[cache_key] = {
        'results': results,
        'timestamp': time.time()
    }

def get_grade(score):
    """Convert numerical score to grade."""
    if score >= 90:
        return {'grade': 'Excellent', 'color': '#2ecc71'}
    elif score >= 80:
        return {'grade': 'Good', 'color': '#27ae60'}
    elif score >= 70:
        return {'grade': 'Average', 'color': '#f1c40f'}
    elif score >= 50:
        return {'grade': 'Poor', 'color': '#e67e22'}
    elif score >= 30:
        return {'grade': 'Very Poor', 'color': '#e74c3c'}
    else:
        return {'grade': 'Critical', 'color': '#c0392b'}

def calculate_seo_score(results):
    """Calculate overall SEO score and grades for each category."""
    score_mapping = {
        'good': 100,
        'warning': 50,
        'error': 0
    }
    
    category_scores = {}
    overall_total = 0
    overall_items = 0
    
    for category, items in results.items():
        if isinstance(items, list) and items:
            category_total = 0
            category_items = 0
            
            for item in items:
                if isinstance(item, dict) and 'status' in item:
                    score = score_mapping.get(item['status'], 0)
                    category_total += score
                    category_items += 1
                    overall_total += score
                    overall_items += 1
            
            if category_items > 0:
                category_score = round((category_total / (category_items * 100)) * 100)
                category_scores[category] = {
                    'score': category_score,
                    'grade': get_grade(category_score)
                }
    
    overall_score = round((overall_total / (overall_items * 100)) * 100) if overall_items > 0 else 0
    
    return {
        'overall': {
            'score': overall_score,
            'grade': get_grade(overall_score)
        },
        'categories': category_scores
    }

def check_page_speed(url):
    """Check page loading speed and performance metrics."""
    try:
        start_time = time.time()
        response = requests.get(url)
        load_time = time.time() - start_time
        
        return {
            "status": "good" if load_time < 2 else "warning" if load_time < 4 else "error",
            "message": "Page load time",
            "details": f"Page loaded in {load_time:.2f} seconds"
        }
    except Exception as e:
        logger.error(f"Error checking page speed: {str(e)}")
        return {
            "status": "error",
            "message": "Page speed check failed",
            "details": str(e)
        }

def check_structured_data(soup):
    """Check for structured data and JSON-LD implementation."""
    results = []
    
    # Check for JSON-LD
    json_ld = soup.find_all('script', type='application/ld+json')
    if json_ld:
        results.append({
            "status": "good",
            "message": "JSON-LD found",
            "details": f"Found {len(json_ld)} JSON-LD implementations"
        })
    else:
        results.append({
            "status": "warning",
            "message": "No JSON-LD found",
            "details": "Consider adding JSON-LD for better search results"
        })
    
    # Check for other structured data
    microdata = soup.find_all(attrs={"itemtype": True})
    if microdata:
        results.append({
            "status": "good",
            "message": "Microdata found",
            "details": f"Found {len(microdata)} microdata elements"
        })
    
    return results

# Helper functions for SEO analysis
def check_canonical_tags(soup):
    """Check for canonical tags and proper implementation."""
    canonical = soup.find('link', {'rel': 'canonical'})
    if canonical:
        return {
            "status": "good",
            "message": "Canonical tag found",
            "details": f"Canonical URL: {canonical.get('href', '')}"
        }
    return {
        "status": "warning",
        "message": "No canonical tag found",
        "details": "Consider adding a canonical tag to prevent duplicate content issues"
    }

def check_hreflang_tags(soup):
    """Check for hreflang tags for multilingual SEO."""
    hreflang_tags = soup.find_all('link', {'rel': 'alternate', 'hreflang': True})
    if hreflang_tags:
        return {
            "status": "good",
            "message": "Hreflang tags found",
            "details": f"Found {len(hreflang_tags)} language alternatives"
        }
    return {
        "status": "info",
        "message": "No hreflang tags found",
        "details": "Add hreflang tags if your site supports multiple languages"
    }

def analyze_readability(text):
    """Analyze content readability using a basic approach."""
    try:
        # Count sentences, words, and syllables
        sentences = len(re.split(r'[.!?]+', text))
        words = len(text.split())
        
        if words == 0 or sentences == 0:
            return {
                "status": "warning",
                "message": "Content too short for readability analysis",
                "details": "Add more content for accurate readability scoring"
            }
        
        # Calculate words per sentence
        words_per_sentence = words / sentences
        
        # Basic readability assessment
        if words_per_sentence > 25:
            status = "warning"
            message = "Sentences may be too long"
            details = f"Average {words_per_sentence:.1f} words per sentence. Aim for 15-20 words."
        elif words_per_sentence < 10:
            status = "warning"
            message = "Sentences may be too short"
            details = f"Average {words_per_sentence:.1f} words per sentence. Aim for 15-20 words."
        else:
            status = "good"
            message = "Good sentence length"
            details = f"Average {words_per_sentence:.1f} words per sentence"
        
        return {
            "status": status,
            "message": message,
            "details": details
        }
    except Exception as e:
        logger.error(f"Error analyzing readability: {str(e)}")
        return {
            "status": "error",
            "message": "Readability analysis failed",
            "details": str(e)
        }

def check_social_media_presence(soup):
    """Check for social media integration and sharing options."""
    results = []
    
    # Check Open Graph tags
    og_tags = soup.find_all('meta', property=re.compile('^og:'))
    if og_tags:
        results.append({
            "status": "good",
            "message": "Open Graph tags found",
            "details": f"Found {len(og_tags)} Open Graph tags"
        })
    
    # Check Twitter Card tags
    twitter_tags = soup.find_all('meta', attrs={'name': re.compile('^twitter:')})
    if twitter_tags:
        results.append({
            "status": "good",
            "message": "Twitter Card tags found",
            "details": f"Found {len(twitter_tags)} Twitter Card tags"
        })
    
    # Check for social media links
    social_patterns = r'facebook\.com|twitter\.com|linkedin\.com|instagram\.com'
    social_links = soup.find_all('a', href=re.compile(social_patterns))
    if social_links:
        results.append({
            "status": "good",
            "message": "Social media links found",
            "details": f"Found {len(social_links)} social media links"
        })
    
    return results

def check_local_seo(soup):
    """Check for local SEO elements."""
    results = []
    
    # Check for address information
    address = soup.find('address')
    if address:
        results.append({
            "status": "good",
            "message": "Business address found",
            "details": "Address tag properly implemented"
        })
    
    # Check for schema.org LocalBusiness
    local_business = soup.find(attrs={"itemtype": re.compile("schema.org/LocalBusiness")})
    if local_business:
        results.append({
            "status": "good",
            "message": "Local Business schema found",
            "details": "Schema.org LocalBusiness markup implemented"
        })
    
    return results

def get_page_size(url):
    try:
        response = requests.get(url, stream=True)
        size = len(response.content)
        return size / 1024  # Convert to KB
    except:
        return 0

def check_ssl(url):
    parsed_url = urlparse(url)
    hostname = parsed_url.netloc
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                return True, cert.get('notAfter', '')
    except:
        return False, None

def check_robots_txt(url):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_url = f"{base_url}/robots.txt"
    try:
        response = requests.get(robots_url)
        if response.status_code == 200:
            return True, response.text
        return False, None
    except:
        return False, None

def check_sitemap(url):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    sitemap_url = f"{base_url}/sitemap.xml"
    try:
        response = requests.get(sitemap_url)
        if response.status_code == 200:
            # Simple count of URL tags in the sitemap
            url_count = response.text.count('<url>')
            return True, url_count
        return False, 0
    except:
        return False, 0

def calculate_keyword_density(text, keyword):
    if not text or not keyword:
        return 0
    words = text.lower().split()
    keyword = keyword.lower()
    keyword_count = sum(1 for word in words if word == keyword)
    if len(words) == 0:
        return 0
    return (keyword_count / len(words)) * 100

def analyze_meta_tags(soup):
    results = []
    
    # Title analysis
    title = soup.title.string if soup.title else None
    if not title:
        results.append({
            "status": "error",
            "message": "Missing title tag",
            "details": "Every page should have a unique title tag"
        })
    elif len(title) < 30:
        results.append({
            "status": "warning",
            "message": "Title tag is too short",
            "details": f"Current length: {len(title)} characters. Recommended: 50-60 characters"
        })
    elif len(title) > 60:
        results.append({
            "status": "warning",
            "message": "Title tag is too long",
            "details": f"Current length: {len(title)} characters. Recommended: 50-60 characters"
        })
    else:
        results.append({
            "status": "good",
            "message": "Title tag length is optimal",
            "details": f"Current length: {len(title)} characters"
        })

    # Meta description analysis
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if not meta_desc:
        results.append({
            "status": "error",
            "message": "Missing meta description",
            "details": "Every page should have a meta description"
        })
    elif meta_desc.get('content'):
        desc_length = len(meta_desc['content'])
        if desc_length < 120:
            results.append({
                "status": "warning",
                "message": "Meta description is too short",
                "details": f"Current length: {desc_length} characters. Recommended: 120-160 characters"
            })
        elif desc_length > 160:
            results.append({
                "status": "warning",
                "message": "Meta description is too long",
                "details": f"Current length: {desc_length} characters. Recommended: 120-160 characters"
            })
        else:
            results.append({
                "status": "good",
                "message": "Meta description length is optimal",
                "details": f"Current length: {desc_length} characters"
            })

    # Check viewport meta tag
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not viewport:
        results.append({
            "status": "error",
            "message": "Missing viewport meta tag",
            "details": "Mobile-friendly pages should have a viewport meta tag"
        })
    else:
        results.append({
            "status": "good",
            "message": "Viewport meta tag present",
            "details": f"Content: {viewport.get('content', '')}"
        })

    # Check social media meta tags
    og_title = soup.find('meta', attrs={'property': 'og:title'})
    og_desc = soup.find('meta', attrs={'property': 'og:description'})
    og_image = soup.find('meta', attrs={'property': 'og:image'})
    twitter_card = soup.find('meta', attrs={'name': 'twitter:card'})

    if not og_title or not og_desc or not og_image:
        results.append({
            "status": "warning",
            "message": "Missing Open Graph meta tags",
            "details": "Open Graph meta tags improve social media sharing"
        })
    else:
        results.append({
            "status": "good",
            "message": "Open Graph meta tags present",
            "details": "All required Open Graph meta tags found"
        })

    if not twitter_card:
        results.append({
            "status": "warning",
            "message": "Missing Twitter Card meta tags",
            "details": "Twitter Card meta tags improve Twitter sharing"
        })
    else:
        results.append({
            "status": "good",
            "message": "Twitter Card meta tags present",
            "details": f"Twitter card type: {twitter_card.get('content', '')}"
        })

    # Check for schema markup
    schema_tags = soup.find_all(['script', 'div'], attrs={'type': 'application/ld+json'})
    if not schema_tags:
        results.append({
            "status": "warning",
            "message": "No Schema.org markup found",
            "details": "Schema markup helps search engines understand your content"
        })
    else:
        results.append({
            "status": "good",
            "message": "Schema.org markup found",
            "details": f"Found {len(schema_tags)} schema markup elements"
        })

    return results

def analyze_headers(soup):
    results = []
    
    # H1 analysis
    h1_tags = soup.find_all('h1')
    if not h1_tags:
        results.append({
            "status": "error",
            "message": "Missing H1 tag",
            "details": "Every page should have one H1 tag"
        })
    elif len(h1_tags) > 1:
        results.append({
            "status": "warning",
            "message": "Multiple H1 tags found",
            "details": f"Found {len(h1_tags)} H1 tags. Recommended: 1 H1 tag per page"
        })
    else:
        results.append({
            "status": "good",
            "message": "H1 tag usage is optimal",
            "details": "Page has exactly one H1 tag"
        })

    # Header hierarchy analysis
    header_counts = {
        'h2': len(soup.find_all('h2')),
        'h3': len(soup.find_all('h3')),
        'h4': len(soup.find_all('h4'))
    }
    
    results.append({
        "status": "good",
        "message": "Header tag distribution",
        "details": f"H2: {header_counts['h2']}, H3: {header_counts['h3']}, H4: {header_counts['h4']}"
    })

    return results

def analyze_images(soup):
    results = []
    images = soup.find_all('img')
    
    if not images:
        results.append({
            "status": "warning",
            "message": "No images found",
            "details": "Consider adding relevant images to enhance content"
        })
        return results

    missing_alt = 0
    total_images = len(images)
    
    for img in images:
        if not img.get('alt'):
            missing_alt += 1

    if missing_alt > 0:
        results.append({
            "status": "warning",
            "message": "Images missing alt text",
            "details": f"{missing_alt} out of {total_images} images are missing alt text"
        })
    else:
        results.append({
            "status": "good",
            "message": "All images have alt text",
            "details": f"All {total_images} images have alt text"
        })

    return results

def analyze_links(soup):
    results = []
    links = soup.find_all('a')
    
    if not links:
        results.append({
            "status": "warning",
            "message": "No links found",
            "details": "Consider adding internal and external links"
        })
        return results

    internal_links = 0
    external_links = 0
    broken_links = 0
    
    for link in links:
        href = link.get('href')
        if href:
            if href.startswith('http'):
                external_links += 1
            else:
                internal_links += 1

    results.append({
        "status": "good",
        "message": "Link distribution",
        "details": f"Internal links: {internal_links}, External links: {external_links}"
    })

    return results

def analyze_content(soup):
    results = []
    
    # Get all text content
    text_content = soup.get_text()
    words = text_content.split()
    word_count = len(words)
    
    if word_count < 300:
        results.append({
            "status": "warning",
            "message": "Content length is too short",
            "details": f"Current word count: {word_count}. Recommended: At least 300 words"
        })
    else:
        results.append({
            "status": "good",
            "message": "Content length is good",
            "details": f"Current word count: {word_count}"
        })

    return results

def analyze_mobile_friendly(soup):
    results = []
    
    # Check viewport meta tag
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not viewport:
        results.append({
            "status": "error",
            "message": "Missing viewport meta tag",
            "details": "Add viewport meta tag for mobile responsiveness"
        })
    else:
        results.append({
            "status": "good",
            "message": "Viewport meta tag found",
            "details": "Page is configured for mobile devices"
        })

    return results

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        logger.info(f"Received URL for analysis: {url}")
        
        if not url:
            logger.warning("Empty URL submitted")
            flash('Please enter a URL', 'error')
            return render_template_string(HTML_TEMPLATE)
            
        # Add scheme if not present
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            logger.info(f"Added https:// to URL: {url}")
            
        if not validators.url(url):
            logger.warning(f"Invalid URL submitted: {url}")
            flash('Please enter a valid URL', 'error')
            return render_template_string(HTML_TEMPLATE)
            
        try:
            logger.info(f"Starting analysis for {url}")
            
            # Check cache first
            cached_results = get_cached_analysis(url)
            if cached_results:
                logger.info(f"Using cached results for {url}")
                return render_template_string(HTML_TEMPLATE, 
                    results=cached_results['results'],
                    raw_results=cached_results['raw_results'],
                    url=url)
            
            # Fetch the URL with a timeout and ignore SSL verification
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            logger.info(f"Successfully fetched URL: {url}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Store raw results for detailed view
            raw_results = {}
            
            # Initialize results dictionary
            results = {}
            
            try:
                raw_results['meta_tags'] = analyze_meta_tags(soup)
                results['meta_tags'] = raw_results['meta_tags']
                logger.info("Completed meta tags analysis")
            except Exception as e:
                logger.error(f"Error in meta tags analysis: {str(e)}")
                results['meta_tags'] = []
            
            try:
                raw_results['headers'] = analyze_headers(soup)
                results['headers'] = raw_results['headers']
                logger.info("Completed headers analysis")
            except Exception as e:
                logger.error(f"Error in headers analysis: {str(e)}")
                results['headers'] = []
            
            try:
                raw_results['images'] = analyze_images(soup)
                results['images'] = raw_results['images']
                logger.info("Completed images analysis")
            except Exception as e:
                logger.error(f"Error in images analysis: {str(e)}")
                results['images'] = []
            
            try:
                raw_results['links'] = analyze_links(soup)
                results['links'] = raw_results['links']
                logger.info("Completed links analysis")
            except Exception as e:
                logger.error(f"Error in links analysis: {str(e)}")
                results['links'] = []
            
            try:
                raw_results['content'] = analyze_content(soup)
                results['content'] = raw_results['content']
                logger.info("Completed content analysis")
            except Exception as e:
                logger.error(f"Error in content analysis: {str(e)}")
                results['content'] = []
            
            try:
                raw_results['mobile_friendly'] = analyze_mobile_friendly(soup)
                results['mobile_friendly'] = raw_results['mobile_friendly']
                logger.info("Completed mobile friendly analysis")
            except Exception as e:
                logger.error(f"Error in mobile friendly analysis: {str(e)}")
                results['mobile_friendly'] = []
            
            try:
                raw_results['structured_data'] = check_structured_data(soup)
                results['structured_data'] = raw_results['structured_data']
                logger.info("Completed structured data analysis")
            except Exception as e:
                logger.error(f"Error in structured data analysis: {str(e)}")
                results['structured_data'] = []
            
            # Calculate score
            score = calculate_seo_score(results)
            logger.info(f"Calculated SEO score: {score}")
            
            # Cache results with raw data
            cache_analysis(url, {'results': score, 'raw_results': raw_results})
            logger.info(f"Analysis completed for {url}")
            
            return render_template_string(HTML_TEMPLATE, 
                results=score,
                raw_results=raw_results,
                url=url)
            
        except requests.RequestException as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            flash(f"Error fetching URL: {str(e)}", 'error')
            return render_template_string(HTML_TEMPLATE)
        except Exception as e:
            logger.error(f"Error analyzing {url}: {str(e)}")
            flash(f"Error analyzing URL: {str(e)}", 'error')
            return render_template_string(HTML_TEMPLATE)
    
    return render_template_string(HTML_TEMPLATE)

# HTML template as a string
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced SEO Analysis Tool</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #2ecc71;
            --warning-color: #f1c40f;
            --error-color: #e74c3c;
            --background-color: #ecf0f1;
            --card-background: white;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: var(--background-color);
            color: var(--primary-color);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: var(--card-background);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        header {
            text-align: center;
            margin-bottom: 30px;
            padding: 30px;
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            border-radius: 12px;
        }

        .input-section {
            text-align: center;
            margin-bottom: 30px;
            position: relative;
        }

        input[type="text"] {
            width: 80%;
            padding: 15px;
            margin: 8px 0;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s ease;
        }

        input[type="text"]:focus {
            border-color: var(--secondary-color);
            box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
            outline: none;
        }

        button {
            background-color: var(--secondary-color);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s ease;
        }

        button:hover {
            background-color: #2980b9;
            transform: translateY(-2px);
        }

        .summary-score {
            text-align: center;
            margin: 40px 0;
            padding: 30px;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .grade-circle {
            width: 150px;
            height: 150px;
            border-radius: 50%;
            margin: 20px auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            color: white;
            position: relative;
            transition: all 0.3s ease;
        }

        .grade-label {
            font-size: 36px;
            margin-bottom: 5px;
        }

        .score-value {
            font-size: 20px;
            opacity: 0.9;
        }

        .category-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }

        .category-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .category-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        .category-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }

        .category-title {
            font-size: 18px;
            font-weight: bold;
            color: var(--primary-color);
        }

        .category-grade {
            font-size: 24px;
            font-weight: bold;
        }

        .category-score {
            font-size: 16px;
            color: #666;
        }

        .flash-messages {
            margin: 20px 0;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            background-color: var(--error-color);
            color: white;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                transform: translateY(-20px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            input[type="text"] {
                width: 90%;
            }

            .category-grid {
                grid-template-columns: 1fr;
            }
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            overflow-y: auto;
        }

        .modal-content {
            background-color: white;
            margin: 50px auto;
            padding: 30px;
            width: 90%;
            max-width: 800px;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            position: relative;
            animation: slideDown 0.3s ease;
        }

        @keyframes slideDown {
            from {
                transform: translateY(-100px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }

        .close-modal {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 24px;
            cursor: pointer;
            color: #666;
            transition: color 0.3s ease;
        }

        .close-modal:hover {
            color: var(--error-color);
        }

        .detail-item {
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 8px;
            background-color: #f8f9fa;
            border-left: 4px solid;
            transition: all 0.2s ease;
            cursor: pointer;
        }

        .detail-item:hover {
            transform: translateX(5px);
            background-color: #f1f3f5;
        }

        .detail-item.good {
            border-left-color: var(--success-color);
        }

        .detail-item.warning {
            border-left-color: var(--warning-color);
        }

        .detail-item.error {
            border-left-color: var(--error-color);
        }

        .detail-item h4 {
            margin: 0;
            color: var(--primary-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .detail-item p {
            margin: 10px 0 0 0;
            color: #666;
        }

        .detail-content {
            display: none;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #eee;
        }

        .detail-content.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .detail-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 14px;
        }

        .detail-table th,
        .detail-table td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }

        .detail-table th {
            font-weight: 600;
            color: var(--primary-color);
            background-color: #f8f9fa;
        }

        .detail-table tr:hover {
            background-color: #f8f9fa;
        }

        .detail-toggle {
            color: #666;
            cursor: pointer;
            transition: transform 0.3s ease;
        }

        .detail-toggle.active {
            transform: rotate(180deg);
        }

        .detail-meta {
            display: flex;
            gap: 15px;
            margin-top: 10px;
            font-size: 14px;
            color: #666;
        }

        .detail-meta-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .detail-meta-item i {
            font-size: 12px;
        }

        .issue-location {
            display: inline-block;
            padding: 2px 6px;
            background-color: #e9ecef;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            color: #495057;
            margin-right: 5px;
        }

        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            margin-right: 5px;
            background-color: #e9ecef;
            color: #495057;
        }

        .tag.critical {
            background-color: #fee2e2;
            color: #991b1b;
        }

        .tag.important {
            background-color: #fef3c7;
            color: #92400e;
        }

        .tag.info {
            background-color: #dbeafe;
            color: #1e40af;
        }

        .suggestions {
            margin-top: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }

        .suggestions h5 {
            margin: 0 0 5px 0;
            color: var(--primary-color);
        }

        .suggestions ul {
            margin: 0;
            padding-left: 20px;
        }

        .suggestions li {
            margin: 5px 0;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Advanced SEO Analysis Tool</h1>
            <p>Enter a URL to analyze its SEO performance</p>
        </header>

        <div class="input-section">
            <form method="POST" action="/">
                <input type="text" name="url" placeholder="Enter website URL (e.g., https://example.com)" required>
                <button type="submit">Analyze</button>
            </form>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash-messages">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% if results %}
            <div class="summary-score">
                <h2>Overall SEO Performance</h2>
                <div class="grade-circle" style="background-color: {{ results.overall.grade.color }}">
                    <div class="grade-label">{{ results.overall.grade.grade }}</div>
                    <div class="score-value">{{ results.overall.score }}%</div>
                </div>
            </div>

            <div class="category-grid">
                {% for category, score in results.categories.items() %}
                    {% if score %}
                        <div class="category-card" onclick="showDetails('{{ category }}')">
                            <div class="category-header">
                                <div class="category-title">{{ category.replace('_', ' ').title() }}</div>
                                <div class="category-grade" style="color: {{ score.grade.color }}">
                                    {{ score.grade.grade }}
                                </div>
                            </div>
                            <div class="category-score">
                                Score: {{ score.score }}%
                            </div>
                        </div>
                    {% endif %}
                {% endfor %}
            </div>

            <!-- Modal for detailed view -->
            <div id="detailsModal" class="modal">
                <div class="modal-content">
                    <span class="close-modal" onclick="closeModal()">&times;</span>
                    <div class="modal-header">
                        <h3 id="modalTitle"></h3>
                    </div>
                    <div id="modalDetails"></div>
                </div>
            </div>
        {% endif %}
    </div>

    <script>
        // Store raw results in JavaScript
        const rawResults = {{ raw_results|tojson|safe if raw_results else '{}' }};

        function formatDetailContent(item, category) {
            let detailContent = '';
            
            // Add specific content based on category
            switch(category) {
                case 'headers':
                    detailContent = `
                        <div class="detail-meta">
                            <div class="detail-meta-item">
                                <i class="fas fa-code"></i> Tag: <span class="issue-location">${item.tag || 'N/A'}</span>
                            </div>
                            ${item.level ? `
                                <div class="detail-meta-item">
                                    <i class="fas fa-layer-group"></i> Level: H${item.level}
                                </div>
                            ` : ''}
                        </div>
                        ${item.text ? `
                            <div class="detail-table-wrapper">
                                <table class="detail-table">
                                    <tr>
                                        <th>Content</th>
                                        <td>${item.text}</td>
                                    </tr>
                                </table>
                            </div>
                        ` : ''}
                    `;
                    break;
                
                case 'links':
                    detailContent = `
                        <div class="detail-meta">
                            <div class="detail-meta-item">
                                <i class="fas fa-link"></i> URL: <span class="issue-location">${item.url || 'N/A'}</span>
                            </div>
                            ${item.type ? `
                                <div class="detail-meta-item">
                                    <i class="fas fa-tag"></i> Type: ${item.type}
                                </div>
                            ` : ''}
                        </div>
                        ${item.anchor_text ? `
                            <div class="detail-table-wrapper">
                                <table class="detail-table">
                                    <tr>
                                        <th>Anchor Text</th>
                                        <td>${item.anchor_text}</td>
                                    </tr>
                                </table>
                            </div>
                        ` : ''}
                    `;
                    break;
                
                case 'images':
                    detailContent = `
                        <div class="detail-meta">
                            <div class="detail-meta-item">
                                <i class="fas fa-image"></i> Source: <span class="issue-location">${item.src || 'N/A'}</span>
                            </div>
                        </div>
                        <div class="detail-table-wrapper">
                            <table class="detail-table">
                                ${item.alt ? `
                                    <tr>
                                        <th>Alt Text</th>
                                        <td>${item.alt}</td>
                                    </tr>
                                ` : ''}
                                ${item.dimensions ? `
                                    <tr>
                                        <th>Dimensions</th>
                                        <td>${item.dimensions}</td>
                                    </tr>
                                ` : ''}
                            </table>
                        </div>
                    `;
                    break;
                
                default:
                    if (item.details) {
                        detailContent = `
                            <div class="suggestions">
                                <h5>Details:</h5>
                                <p>${item.details}</p>
                            </div>
                        `;
                    }
            }
            
            // Add suggestions if available
            if (item.suggestions) {
                detailContent += `
                    <div class="suggestions">
                        <h5>How to Fix:</h5>
                        <ul>
                            ${Array.isArray(item.suggestions) 
                                ? item.suggestions.map(s => `<li>${s}</li>`).join('')
                                : `<li>${item.suggestions}</li>`
                            }
                        </ul>
                    </div>
                `;
            }
            
            return detailContent;
        }

        function showDetails(category) {
            const modal = document.getElementById('detailsModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalDetails = document.getElementById('modalDetails');
            
            modalTitle.textContent = category.replace('_', ' ').title() + ' Details';
            modalDetails.innerHTML = '';

            const items = rawResults[category] || [];
            if (items.length === 0) {
                modalDetails.innerHTML = '<p>No details available for this category.</p>';
            } else {
                // Add summary counts
                const counts = {
                    good: items.filter(item => item.status === 'good').length,
                    warning: items.filter(item => item.status === 'warning').length,
                    error: items.filter(item => item.status === 'error').length
                };

                const summaryHtml = `
                    <div class="detail-summary">
                        <div>
                            <span class="status-icon good"><i class="fas fa-check-circle"></i> ${counts.good}</span>
                            <span class="status-icon warning"><i class="fas fa-exclamation-circle"></i> ${counts.warning}</span>
                            <span class="status-icon error"><i class="fas fa-times-circle"></i> ${counts.error}</span>
                        </div>
                        <div class="detail-count">Total: ${items.length} items</div>
                    </div>
                `;
                modalDetails.innerHTML = summaryHtml;

                // Add individual items
                items.forEach((item, index) => {
                    const detailHtml = `
                        <div class="detail-item ${item.status}" onclick="toggleDetail(${index})">
                            <h4>
                                <span>
                                    <i class="fas fa-${item.status === 'good' ? 'check' : item.status === 'warning' ? 'exclamation' : 'times'}-circle status-icon ${item.status}"></i>
                                    ${item.message}
                                </span>
                                <i class="fas fa-chevron-down detail-toggle" id="toggle-${index}"></i>
                            </h4>
                            <div class="detail-content" id="content-${index}">
                                ${formatDetailContent(item, category)}
                            </div>
                        </div>
                    `;
                    modalDetails.innerHTML += detailHtml;
                });
            }

            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        }

        function toggleDetail(index) {
            const content = document.getElementById(`content-${index}`);
            const toggle = document.getElementById(`toggle-${index}`);
            content.classList.toggle('active');
            toggle.classList.toggle('active');
        }

        function closeModal() {
            const modal = document.getElementById('detailsModal');
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('detailsModal');
            if (event.target === modal) {
                closeModal();
            }
        }

        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeModal();
            }
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    try:
        # Get the hostname
        hostname = socket.gethostname()
        # Get the IP address
        ip_address = socket.gethostbyname(hostname)
        print(f"Server running at http://{ip_address}:5000")
        app.run(host=ip_address, port=5000, debug=True)
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        app.run(debug=True)
