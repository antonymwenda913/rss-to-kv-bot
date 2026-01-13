import feedparser
import json
import time
import schedule
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
RSS_URL = "https://jumitech.co.ke/feeds/posts/default?alt=rss"  # Verify this is your actual feed URL
# --- NEW WAY (SAFE USING GITHUB SECRETS) ---
import os

EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# We split the string by commas to turn it back into a list
recipients_raw = os.environ.get('RECIPIENT_LIST')
RECIPIENTS = [email.strip() for email in recipients_raw.split(',')] 

# File to remember sent posts
HISTORY_FILE = "sent_posts.txt"

def load_sent_posts():
    """Loads the IDs of posts we have already processed."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_sent_post(post_id):
    """Saves a new post ID so we don't send it again."""
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{post_id}\n")

def extract_arrays_from_html(html_content):
    """
    Scans HTML content to find 'Arrays':
    1. Unordered Lists (<ul>)
    2. Numbered Lists (<ol>)
    3. Image URLs (<img>)
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    extracted_data = {
        "detected_lists": [],
        "images": []
    }

    # 1. Extract Bullet Points/Numbered Lists
    for list_tag in soup.find_all(['ul', 'ol']):
        # Create a clean list of the text inside the list items
        clean_list = [li.get_text(strip=True) for li in list_tag.find_all('li')]
        if clean_list:
            extracted_data["detected_lists"].append(clean_list)

    # 2. Extract Images
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            extracted_data["images"].append(src)

    return extracted_data

def send_email(subject, body, file_path, recipients):
    """Sends the email with the HTML/JSON attachment."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Attach the file
        attachment = open(file_path, "rb")
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(file_path)}")
        msg.attach(part)

        # Send
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {len(recipients)} recipients.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def job():
    print(f"[{time.strftime('%H:%M:%S')}] Checking feed...")
    
    # 1. Fetch the Feed
    feed = feedparser.parse(RSS_URL)
    sent_posts = load_sent_posts()
    
    if not feed.entries:
        print("No entries found. Check URL.")
        return

    # 2. Look at the NEWEST post first
    latest_post = feed.entries[0]
    post_id = latest_post.get('id', latest_post.link) # Use Link as ID if ID is missing

    # 3. Check if we've seen it
    if post_id in sent_posts:
        print("No new posts found.")
        return
    
    print(f"🚀 New Post Found: {latest_post.title}")

    # 4. Extract Data & Arrays
    content = latest_post.get('content', [{'value': latest_post.summary}])[0]['value']
    extra_data = extract_arrays_from_html(content)
    
    post_data = {
        "title": latest_post.title,
        "link": latest_post.link,
        "published": latest_post.published,
        "tags": [tag.term for tag in latest_post.get('tags', [])], # Array of tags
        "images": extra_data['images'], # Array of images
        "content_lists": extra_data['detected_lists'], # Array of lists found in text
        "full_content": content
    }

    # 5. Create JSON file (saved as .html for easy viewing)
    json_output = json.dumps(post_data, indent=4)
    filename = f"post_update_{int(time.time())}.html"
    
    # We wrap the JSON in simple HTML so it's easy to read/edit
    html_content = f"""
    <html>
    <body>
        <h2>New Post Data for Editing</h2>
        <p>Copy the code below for Cloudflare KV:</p>
        <textarea style="width:100%; height:500px;">{json_output}</textarea>
    </body>
    </html>
    """

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 6. Send Email
    email_body = f"A new post '{latest_post.title}' has been published. Please find the JSON extraction attached."
    send_email(f"New RSS Post: {latest_post.title}", email_body, filename, RECIPIENTS)

    # 7. Remember this post
    save_sent_post(post_id)

# --- SCHEDULE ---
# Check every 5 minutes
schedule.every(5).minutes.do(job)

# Run once immediately to test (Optional)
job() 

print("🤖 Bot is running. Press Ctrl+C to stop.")
while True:
    schedule.run_pending()
    time.sleep(1)
