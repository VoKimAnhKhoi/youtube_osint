import os
import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from transformers import pipeline
from telegram import Bot
import schedule
import time
import asyncio
from YOUTUBE_OSINT import init_db, predict_trending_videos, send_report

# Kiểm tra và cài đặt TensorFlow hoặc PyTorch
try:
    import tensorflow as tf
    print(f"TensorFlow version: {tf.__version__}")
except ImportError:
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
    except ImportError:
        raise RuntimeError("Cần cài đặt TensorFlow hoặc PyTorch. "
                           "Sử dụng lệnh 'pip install tensorflow' hoặc 'pip install torch'.")

# YouTube API
youtube_api_key = ""  # Thay thế bằng API key của bạn
youtube = build("youtube", "v3", developerKey=youtube_api_key)

# Telegram Bot
telegram_token = ""  # Thay thế bằng token của bạn
telegram_chat_id = ""  # Thay thế bằng chat ID của bạn
bot = Bot(token=telegram_token)

# Hugging Face summarization pipeline
summarizer = pipeline("summarization")

def sanitize_text(text):
    """
    Replace problematic characters or ensure proper encoding for UTF-8.
    """
    try:
        return text.encode('utf-8', 'ignore').decode('utf-8')
    except Exception as e:
        print(f"Error sanitizing text: {e}")
        return text

class YouTubeToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Tool")
        
        # Tạo font hỗ trợ tiếng Việt
        vietnamese_font = tkFont.Font(family="Arial", size=10)

        # Entry for YouTube URLs
        self.url_label = tk.Label(root, text="YouTube URLs (comma-separated):", font=vietnamese_font)
        self.url_label.pack()
        self.url_entry = tk.Entry(root, width=50, font=vietnamese_font)
        self.url_entry.pack()
        
        # Button to process videos
        self.process_button = tk.Button(root, text="Xử lý video", command=self.process_videos, font=vietnamese_font)
        self.process_button.pack()
        
        # Button to send trending videos
        self.trending_button = tk.Button(root, text="Gửi video thịnh hành", command=self.send_trending_videos, font=vietnamese_font)
        self.trending_button.pack()

        # Button to send message to Telegram
        self.send_telegram_button = tk.Button(root, text="Gửi tin nhắn Telegram", command=self.send_to_telegram_from_input, font=vietnamese_font)
        self.send_telegram_button.pack()

        # Button to get video info
        self.video_info_button = tk.Button(root, text="Get Video Info", command=self.get_video_info, font=vietnamese_font)
        self.video_info_button.pack()

        # Entry for YouTube Channel URL
        self.channel_label = tk.Label(root, text="YouTube Channel URL:", font=vietnamese_font)
        self.channel_label.pack()
        self.channel_entry = tk.Entry(root, width=50, font=vietnamese_font)
        self.channel_entry.pack()

        # Button to process channel
        self.process_channel_button = tk.Button(root, text="Transcript Channel", command=self.process_channel, font=vietnamese_font)
        self.process_channel_button.pack()

        # Text box to display the results
        self.result_text = tk.Text(root, height=20, width=80, font=vietnamese_font)
        self.result_text.pack()

    async def send_to_telegram(self, message, photo_url=None):
        """
        Gửi tin nhắn và hình ảnh qua Telegram.
        """
        try:
            # Chia nhỏ tin nhắn nếu vượt quá giới hạn 4096 ký tự
            max_length = 4096
            chunks = [message[i:i + max_length] for i in range(0, len(message), max_length)]

            for chunk in chunks:
                sanitized_message = sanitize_text(chunk)
                await bot.send_message(chat_id=telegram_chat_id, text=sanitized_message)

            if photo_url:
                await bot.send_photo(chat_id=telegram_chat_id, photo=photo_url)

            print("Message sent to Telegram.")
        except Exception as e:
            print(f"Error sending message to Telegram: {e}")

    def send_to_telegram_from_input(self):
        # Gửi tin nhắn từ input đến Telegram
        message = self.url_entry.get()  # Lấy URL từ input
        if message:
            asyncio.run(self.send_to_telegram(message))  # Gọi hàm gửi tin nhắn
            messagebox.showinfo("Info", "Message sent to Telegram!")
        else:
            messagebox.showwarning("Warning", "Please enter a message.")

    def process_videos(self):
        urls = self.url_entry.get().split(",")
        for url in urls:
            video_id = self.get_video_id(url.strip())
            if video_id:
                transcript = self.get_transcript(video_id)
                comments = self.get_comments(video_id)
                thumbnail_url = self.get_video_thumbnail(video_id)

                if transcript and comments and thumbnail_url:
                    transcript_summary = self.summarize_text(transcript)
                    comments_summary = self.summarize_text(comments)

                    sanitized_message = sanitize_text(
                        f"Video URL: {url}\n\nTranscript Summary:\n{transcript_summary}\n\nComments Summary:\n{comments_summary}"
                    )
                    self.result_text.insert(tk.END, sanitized_message + "\n\n")
                    asyncio.run(self.send_to_telegram(sanitized_message, thumbnail_url))  # Gửi tin nhắn
                else:
                    self.result_text.insert(tk.END, f"Error processing video: {url}\n\n")
            else:
                self.result_text.insert(tk.END, f"Invalid URL: {url}\n\n")
        messagebox.showinfo("Info", "Processing complete!")

    def get_video_id(self, url):
        # Extract video ID from YouTube URL
        try:
            if "v=" in url:  # Standard YouTube URL
                return url.split("v=")[-1].split("&")[0]
            elif "youtu.be/" in url:  # Shortened YouTube URL
                return url.split("youtu.be/")[-1].split("?")[0]
            elif "youtube.com/shorts/" in url:  # YouTube Shorts URL
                return url.split("youtube.com/shorts/")[-1].split("?")[0]
            else:
                return None
        except Exception as e:
            print(f"Error extracting video ID: {e}")
            return None

    def get_video_thumbnail(self, video_id):
        # Get video thumbnail URL for a given video ID
        try:
            request = youtube.videos().list(
                part="snippet",
                id=video_id
            )
            response = request.execute()
            thumbnail_url = response["items"][0]["snippet"]["thumbnails"]["high"]["url"]
            return thumbnail_url
        except Exception as e:
            print(f"Error retrieving thumbnail: {e}")
            return None

    def get_transcript(self, video_id):
        # Get transcript for a given video ID
        try:
            # Attempt to fetch the transcript in English
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            return " ".join([t["text"] for t in transcript])
        except Exception as e:
            print(f"Error retrieving English transcript: {e}")
            try:
                # Fallback to auto-generated Vietnamese transcript
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['vi'])
                return " ".join([t["text"] for t in transcript])
            except Exception as e:
                print(f"Error retrieving Vietnamese transcript: {e}")
                return None

    def get_comments(self, video_id):
        # Get comments for a given video ID
        try:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                textFormat="plainText",
                maxResults=100
            )
            response = request.execute()
            comments = [item["snippet"]["topLevelComment"]["snippet"]["textOriginal"] for item in response["items"]]
            return " ".join(comments)
        except Exception as e:
            print(f"Error retrieving comments: {e}")
            return None

    def summarize_text(self, text):
        # Summarize text using Hugging Face pipeline
        max_chunk_size = 1024  # Maximum token limit for the model
        chunks = [text[i:i + max_chunk_size] for i in range(0, len(text), max_chunk_size)]
        summaries = []

        for chunk in chunks:
            try:
                summary = summarizer(chunk, max_length=150, min_length=30, do_sample=False)
                summaries.append(summary[0]["summary_text"])
            except Exception as e:
                print(f"Error summarizing chunk: {e}")
                summaries.append("[Error summarizing this chunk]")

        # Combine all chunk summaries into a single summary
        return " ".join(summaries)

    def get_trending_videos(self):
        # Get top trending YouTube videos
        try:
            request = youtube.videos().list(
                part="snippet",
                chart="mostPopular",
                regionCode="VN",  # Change region code as needed
                maxResults=20      # Number of trending videos to fetch
            )
            response = request.execute()
            return response["items"]
        except Exception as e:
            print(f"Error retrieving trending videos: {e}")
            return None

    def send_trending_videos(self):
        trending_videos = self.get_trending_videos()
        if trending_videos:
            for video in trending_videos:
                video_url = f"https://www.youtube.com/watch?v={video['id']}"
                thumbnail_url = video["snippet"]["thumbnails"]["high"]["url"]
                title = video["snippet"]["title"]
                description = video["snippet"]["description"]
                message = f"Trending Video: {title}\n{description}\n{video_url}"
                asyncio.run(self.send_to_telegram(message, thumbnail_url))  # Gọi hàm gửi tin nhắn
                self.result_text.insert(tk.END, message + "\n\n")
        else:
            self.result_text.insert(tk.END, "Error fetching trending videos.\n\n")
        messagebox.showinfo("Info", "Trending videos sent!")

    def extract_channel_id(self, url):
        """
        Trích xuất channel_id từ link kênh YouTube hoặc định dạng @username.
        """
        try:
            if "channel/" in url:
                return url.split("channel/")[-1].split("/")[0]
            elif "user/" in url:
                username = url.split("user/")[-1].split("/")[0]
                request = youtube.channels().list(part="id", forUsername=username)
                response = request.execute()
                return response["items"][0]["id"]
            elif url.startswith("@"):
                username = url[1:]
                request = youtube.search().list(
                    part="snippet",
                    q=username,
                    type="channel",
                    maxResults=1
                )
                response = request.execute()
                return response["items"][0]["snippet"]["channelId"]
            else:
                return None
        except Exception as e:
            print(f"Error extracting channel ID: {e}")
            return None

    def process_channel(self):
        """
        Lấy transcript cho toàn bộ video từ một kênh YouTube và gửi qua Telegram.
        """
        channel_url = self.channel_entry.get()
        if not channel_url:
            messagebox.showwarning("Warning", "Please enter a channel URL.")
            return

        # Lấy channel_id từ URL
        channel_id = self.extract_channel_id(channel_url)
        if not channel_id:
            self.result_text.insert(tk.END, "Invalid channel URL.\n")
            return

        # Lấy danh sách video từ kênh
        video_ids = get_channel_videos(channel_id)
        if not video_ids:
            self.result_text.insert(tk.END, "No videos found for the channel.\n")
            return

        # Lấy transcript cho từng video và gửi qua Telegram
        transcripts = get_video_transcripts(video_ids)

        for video_id, transcript in transcripts.items():
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = self.get_video_thumbnail(video_id)

            if transcript:
                sanitized_transcript = sanitize_text(transcript)
                message = (
                    f"Video URL: {video_url}\n\n"
                    f"Transcript:\n{sanitized_transcript}\n"
                )
                self.result_text.insert(tk.END, message + "\n\n")

                # Gửi tin nhắn qua Telegram
                asyncio.run(self.send_to_telegram(message, thumbnail_url))
            else:
                self.result_text.insert(tk.END, f"No transcript available for video {video_id}.\n\n")

        messagebox.showinfo("Info", "Channel processing and Telegram sending complete!")

    def get_video_info(self):
        """
        Lấy thông tin video từ YouTube URL và hiển thị trong giao diện.
        """
        url = self.url_entry.get().strip()
        video_id = self.get_video_id(url)
        if not video_id:
            self.result_text.insert(tk.END, "Invalid YouTube URL.\n")
            return

        try:
            request = youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            )
            response = request.execute()
            if "items" in response and len(response["items"]) > 0:
                video_info = response["items"][0]
                title = video_info["snippet"]["title"]
                description = video_info["snippet"]["description"]
                views = video_info["statistics"].get("viewCount", "N/A")
                likes = video_info["statistics"].get("likeCount", "N/A")
                comments = video_info["statistics"].get("commentCount", "N/A")

                info = (
                    f"Title: {title}\n"
                    f"Description: {description}\n"
                    f"Views: {views}\n"
                    f"Likes: {likes}\n"
                    f"Comments: {comments}\n"
                )
                self.result_text.insert(tk.END, info + "\n\n")
            else:
                self.result_text.insert(tk.END, "No video information found.\n")
        except Exception as e:
            print(f"Error retrieving video info: {e}")
            self.result_text.insert(tk.END, "Error retrieving video information.\n")

def get_channel_videos(channel_id):
    """
    Lấy danh sách video từ một kênh YouTube.
    """
    try:
        video_ids = []
        request = youtube.search().list(
            part="id",
            channelId=channel_id,
            maxResults=10,
            type="video",
            order="date"
        )
        response = request.execute()

        for item in response["items"]:
            video_ids.append(item["id"]["videoId"])

        return video_ids
    except Exception as e:
        print(f"Error retrieving videos from channel: {e}")
        return []

def get_video_transcripts(video_ids):
    """
    Lấy transcript cho danh sách video, hỗ trợ tiếng Anh và tiếng Việt.
    """
    transcripts = {}
    for video_id in video_ids:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            transcripts[video_id] = " ".join([t["text"] for t in transcript])
        except Exception as e:
            print(f"Error retrieving English transcript for video {video_id}: {e}")
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['vi'])
                transcripts[video_id] = " ".join([t["text"] for t in transcript])
            except Exception as e:
                print(f"Error retrieving Vietnamese transcript for video {video_id}: {e}")
                transcripts[video_id] = None
    return transcripts

def run_scheduled_jobs():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeToolApp(root)
    root.mainloop()

def initialize_database():
    try:
        init_db()
        messagebox.showinfo("Thành công", "Cơ sở dữ liệu đã được khởi tạo!")
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể khởi tạo cơ sở dữ liệu: {e}")

def predict_videos():
    try:
        predictions = predict_trending_videos()
        result = "Dự đoán video trending:\n"
        for video_id, growth in predictions:
            result += f"Video {video_id} - Dự báo tăng {growth:,.0f} lượt xem\n"
        messagebox.showinfo("Dự đoán", result)
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể dự đoán video trending: {e}")

async def send_report_async():
    try:
        await send_report()
        messagebox.showinfo("Thành công", "Báo cáo đã được gửi qua Telegram!")
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không thể gửi báo cáo: {e}")

def send_report_button():
    asyncio.run(send_report_async())

# Gửi tin nhắn tiếng Việt có dấu
async def send_vietnamese_message():
    message = "Xin chào! Đây là nội dung tiếng Việt có dấu."
    await bot.send_message(chat_id=telegram_chat_id, text=message)

# Chạy giao diện
root.mainloop()
