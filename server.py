import os
import re
import asyncio
import websockets
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
        return f"Downloaded: {file_path}"
    except Exception as e:
        return f"Failed to download {url}: {e}"

def process_css(css_content, base_url, css_dir):
    """Process CSS content to download linked resources and update paths."""
    url_pattern = re.compile(r'url\((.*?)\)')
    matches = url_pattern.findall(css_content)

    for match in matches:
        match = match.strip('\'"')
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

async def handle_copy(websocket, path):
    try:
        message = await websocket.recv()
        data = json.loads(message)
        url = data.get("url")
        if not url:
            await websocket.send(json.dumps({"message": "Invalid URL", "complete": True}))
            return

        response = requests.get(url)
        response.raise_for_status()
        base_url = url
        html = response.text

        output_dir = 'copied_website'
        output_file = os.path.join(output_dir, 'index.html')
        updated_html = process_html(html, base_url, output_dir)

        ensure_dir(output_file)
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(updated_html)

        await websocket.send(json.dumps({"message": f"Website content successfully copied to {output_file}", "complete": True}))
    except Exception as e:
        await websocket.send(json.dumps({"message": f"An error occurred: {e}", "complete": True}))

async def main():
    async with websockets.serve(handle_copy, "localhost", 8001):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
