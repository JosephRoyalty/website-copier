import os
import re
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

def sanitize_filename(url):
    """Convert a URL to a valid filename."""
    filename = re.sub(r'[^\w\s]', '_', url)
    filename = re.sub(r'\s+', '_', filename)
    return filename

def ensure_dir(file_path):
    """Ensure the directory exists for the given file path."""
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_file(url, file_path):
    """Download a file from a URL and save it to the local file path."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        ensure_dir(file_path)
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Downloaded: {file_path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def process_css(css_content, base_url, css_dir):
    """Process CSS content to download linked resources and update paths."""
    url_pattern = re.compile(r'url\((.*?)\)')
    matches = url_pattern.findall(css_content)

    for match in matches:
        match = match.strip('\'"')  # Remove any surrounding quotes
        resource_url = urljoin(base_url, match)
        resource_filename = sanitize_filename(resource_url)
        resource_path = os.path.join(css_dir, resource_filename)
        download_file(resource_url, resource_path)
        css_content = css_content.replace(match, os.path.join('css', resource_filename))

    return css_content

def process_html(html, base_url, output_dir):
    """Process HTML content and download linked resources."""
    soup = BeautifulSoup(html, 'html.parser')

    # Download all linked CSS files
    for link in soup.find_all('link', href=True):
        href = link['href']
        if link.get('rel') == ['stylesheet']:
            css_url = urljoin(base_url, href)
            css_filename = sanitize_filename(css_url)
            css_path = os.path.join(output_dir, 'css', css_filename)
            css_content = requests.get(css_url).text
            processed_css = process_css(css_content, base_url, os.path.join(output_dir, 'css'))
            with open(css_path, 'w', encoding='utf-8') as css_file:
                css_file.write(processed_css)
            link['href'] = os.path.join('css', css_filename)

    # Download all linked JS files
    for script in soup.find_all('script', src=True):
        src = script['src']
        js_url = urljoin(base_url, src)
        js_filename = sanitize_filename(js_url)
        js_path = os.path.join(output_dir, 'js', js_filename)
        download_file(js_url, js_path)
        script['src'] = os.path.join('js', js_filename)

    # Download all images
    for img in soup.find_all('img', src=True):
        src = img['src']
        img_url = urljoin(base_url, src)
        img_filename = sanitize_filename(img_url)
        img_path = os.path.join(output_dir, 'images', img_filename)
        download_file(img_url, img_path)
        img['src'] = os.path.join('images', img_filename)

    # Download background images specified in inline styles
    for tag in soup.find_all(style=True):
        style = tag['style']
        updated_style = process_css(style, base_url, os.path.join(output_dir, 'css'))
        tag['style'] = updated_style

    # Return the updated HTML with local resource paths
    return str(soup)

def copy_website(url, output_file):
    try:
        response = requests.get(url)
        response.raise_for_status()
        base_url = url
        html = response.text

        # Process and save HTML content
        output_dir = os.path.dirname(output_file)
        updated_html = process_html(html, base_url, output_dir)

        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(updated_html)

        return {"success": True, "message": f"Website content successfully copied to {output_file}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith('/copy'):
            params = parse_qs(urlparse(self.path).query)
            url = params.get('url', [None])[0]
            if url:
                result = copy_website(url, 'copied_website/index.html')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            else:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "No URL provided"}).encode())
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "message": "Not Found"}).encode())

def run(server_class=HTTPServer, handler_class=RequestHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting server on port {port}...')
    httpd.serve_forever()

if __name__ == "__main__":
    run()
