import json
import os
import smtplib
import tempfile
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

import bs4
import cloudscraper

# Настройки
BASE_URL = "https://www.azathabar.com"
SENT_LOG_FILE = "sent_articles.json"

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)


def load_sent_articles():
    if os.path.exists(SENT_LOG_FILE):
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Ошибка чтения {SENT_LOG_FILE}: {e}")
    return set()


def save_sent_articles(sent_set):
    try:
        with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_set), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения {SENT_LOG_FILE}: {e}")


def get_latest_articles():
    """Парсит ссылки на статьи с главной страницы."""
    try:
        response = scraper.get(BASE_URL, timeout=20)
        response.raise_for_status()

        soup = bs4.BeautifulSoup(response.content, "html.parser")
        articles = []
        seen_links = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)

            if href.endswith(".html") and len(title) > 10:
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                if full_url not in seen_links:
                    seen_links.add(full_url)
                    articles.append((title, full_url))

        return articles
    except Exception as e:
        print(f"Ошибка при парсинге главной страницы: {e}")
        return []


def parse_and_process_article(url):
    """
    Парсит статью, удаляет мусор и дубликаты картинок,
    скачивает уникальные изображения во временную папку.
    """
    temp_files = []
    images_data = []

    try:
        response = scraper.get(url, timeout=20)
        response.raise_for_status()

        soup = bs4.BeautifulSoup(response.content, "html.parser")
        article_body = soup.find("div", class_="wsw") or soup.find("article")

        if not article_body:
            return "<p>Не удалось извлечь текст статьи.</p>", temp_files, images_data

        # Удаляем скрипты, стили, фреймы, формы и блоки рекомендаций
        for unneeded in article_body.find_all(["script", "style", "iframe", "form", "aside"]):
            unneeded.decompose()

        # Удаляем блоки со связанными статьями (Degişli maglumat)
        for rel_block in article_body.find_all("div", class_=lambda c: c and "related" in c):
            rel_block.decompose()

        processed_img_urls = set()
        img_tags = article_body.find_all("img")

        for img in img_tags:
            src = img.get("src") or img.get("data-src")
            if not src:
                img.decompose()
                continue

            img_url = urljoin(BASE_URL, src)

            # Если эта картинка уже была обработана в статье — удаляем дубликат из HTML
            if img_url in processed_img_urls:
                img.decompose()
                continue

            try:
                img_resp = scraper.get(img_url, timeout=15)
                if img_resp.status_code == 200:
                    processed_img_urls.add(img_url)
                    cid_name = f"img_{len(processed_img_urls)}"

                    ext = os.path.splitext(img_url)[1].split('?')[0] or '.jpg'
                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp_file.write(img_resp.content)
                    tmp_file.close()

                    temp_files.append(tmp_file.name)
                    images_data.append((tmp_file.name, cid_name, img_resp.content))

                    img["src"] = f"cid:{cid_name}"
                    img["style"] = "max-width: 100%; height: auto; display: block; margin: 12px 0;"
                else:
                    img.decompose()
            except Exception as img_err:
                print(f"Не удалось скачать картинку {img_url}: {img_err}")
                img.decompose()

        return str(article_body), temp_files, images_data

    except Exception as e:
        print(f"Ошибка при обработке статьи {url}: {e}")
        return "<p>Ошибка при загрузке содержимого статьи.</p>", temp_files, images_data


def send_email(html_body, article_url, images_data):
    """
    Отправляет письмо с улучшенными стилями текста и читаемым шрифтом.
    Тема письма строго: RF
    """
    msg = MIMEMultipart("related")
    msg["Subject"] = "RF"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    # Красивая обертка для читаемости текста на любом экране
    email_content = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.6;
            color: #222222;
            background-color: #ffffff;
            margin: 0;
            padding: 12px;
          }}
          p {{
            margin-bottom: 1em;
            font-size: 16px;
          }}
          a {{
            color: #0066cc;
          }}
          img {{
            max-width: 100% !important;
            height: auto !important;
          }}
        </style>
      </head>
      <body>
        <div style="font-size: 13px; color: #777777; margin-bottom: 12px;">
            Оригинал статьи: <a href="{article_url}">{article_url}</a>
        </div>
        <hr style="border: 0; border-top: 1px solid #eeeeee; margin-bottom: 16px;">
        <div class="article-content">
            {html_body}
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(email_content, "html", "utf-8"))

    for file_path, cid_name, file_bytes in images_data:
        try:
            mime_img = MIMEImage(file_bytes)
            mime_img.add_header("Content-ID", f"<{cid_name}>")
            mime_img.add_header("Content-Disposition", "inline", filename=os.path.basename(file_path))
            msg.attach(mime_img)
        except Exception as e:
            print(f"Ошибка добавления вложения {file_path}: {e}")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)

    print("Отправлено письмо с темой 'RF'")


def cleanup_temp_files(files_list):
    for file_path in files_list:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Не удалось удалить временный файл {file_path}: {e}")


def main():
    sent_articles = load_sent_articles()
    articles = get_latest_articles()

    if not articles:
        print("Статьи не найдены.")
        return

    new_sent_count = 0
    for title, link in reversed(articles):
        if link in sent_articles:
            continue

        print(f"Обработка новости: {title} ({link})")
        content_html, temp_files, images_data = parse_and_process_article(link)

        try:
            send_email(content_html, link, images_data)
            sent_articles.add(link)
            new_sent_count += 1
        finally:
            cleanup_temp_files(temp_files)

    if new_sent_count > 0:
        save_sent_articles(sent_articles)
        print(f"Обработано и отправлено новых статей: {new_sent_count}")
    else:
        print("Новых статей нет.")


if __name__ == "__main__":
    main()
        
