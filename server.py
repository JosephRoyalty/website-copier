import os
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio
import websockets
from http.server import SimpleHTTPRequestHandler, HTTPServer

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

async def download_file(url, file_path, websocket):
    """Download a file from a URL and save it to the local file path."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        ensure_dir(file_path)
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        await websocket.send(json.dumps({"message": f"Downloaded: {file_path}"}))
    except Exception as e:
        await websocket.send(json.dumps({"message": f"Failed to download {url}: {e}"}))

async def process_css(css_content, base_url, css_dir, websocket):
    """Process CSS content to download linked resources and update paths."""
    url_pattern = re.compile(r'url\((.*?)\)')
    matches = url_pattern.findall(css_content)

    for match in matches:
        match = match.strip('\'"')  # Remove any surrounding quotes
        resource_url = urljoin(base_url, match)
        resource_filename = sanitize_filename(resource_url)
        resource_path = os.path.join(css_dir, resource_filename)
        await download_file(resource_url, resource_path, websocket)
        css_content = css_content.replace(match, os.path.join('css', resource_filename))

    return css_content

async def process_html(html, base_url, output_dir, websocket):
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
            processed_css = await process_css(css_content, base_url, os.path.join(output_dir, 'css'), websocket)
            with open(css_path, 'w', encoding='utf-8') as css_file:
                css_file.write(processed_css)
            link['href'] = os.path.join('css', css_filename)

    # Download all linked JS files
    for script in soup.find_all('script', src=True):
        src = script['src']
        js_url = urljoin(base_url, src)
        js_filename = sanitize_filename(js_url)
        js_path = os.path.join(output_dir, 'js', js_filename)
        await download_file(js_url, js_path, websocket)
        script['src'] = os.path.join('js', js_filename)

    # Download all images
    for img in soup.find_all('img', src=True):
        src = img['src']
        img_url = urljoin(base_url, src)
        img_filename = sanitize_filename(img_url)
        img_path = os.path.join(output_dir, 'images', img_filename)
        await download_file(img_url, img_path, websocket)
        img['src'] = os.path.join('images', img_filename)

    # Download background images specified in inline styles
    for tag in soup.find_all(style=True):
        style = tag['style']
        updated_style = await process_css(style, base_url, os.path.join(output_dir, 'css'), websocket)
        tag['style'] = updated_style

    # Return the updated HTML with local resource paths
    return str(soup)

async def copy_website(url, output_file, websocket):
    try:
        response = requests.get(url)
        response.raise_for_status()
        base_url = url
        html = response.text

        # Process and save HTML content
        output_dir = os.path.dirname(output_file)
        updated_html = await process_html(html, base_url, output_dir, websocket)

        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(updated_html)

        await websocket.send(json.dumps({"message": f"Website content successfully copied to {output_file}", "complete": True}))
    except Exception as e:
        await websocket.send(json.dumps({"message": str(e), "complete": True}))

async def handler(websocket, path):
    data = await websocket.recv()
    params = json.loads(data)
    url = params.get('url')
    if url:
        await copy_website(url, 'copied_website/index.html', websocket)

def run_http_server():
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print('HTTP server running on port 8000...')
    httpd.serve_forever()

async def run_websocket_server():
    async with websockets.serve(handler, "localhost", 8001):
        print("WebSocket server running on port 8001...")
        await asyncio.Future()  # Run forever

def run_servers():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_http_server)
    loop.run_until_complete(run_websocket_server())

if __name__ == "__main__":
    run_servers()
