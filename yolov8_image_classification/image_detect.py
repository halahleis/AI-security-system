import os
import cv2
import smtplib
from ultralytics import YOLO
from email.message import EmailMessage
import RPi.GPIO as GPIO
import pygame
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
gmail_user = os.environ.get("GMAIL_USER")
gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

# Logging Setup
LOG_FILE = "image_detection_log.txt"

def log_event(event_type):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] Detected: {event_type}\n")

# GPIO Setup
GPIO.setmode(GPIO.BCM)
LED_PIN = 18
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

# Sound Setup
pygame.mixer.init()
alarm_sound = pygame.mixer.Sound("assets/alarm.WAV")
alarm_playing = False

# Email Setup Function
def send_email_alert(subject, body):
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = gmail_user
    msg['To'] = gmail_user  # You can change this if needed

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Email sending failed: {e}")

# Camera Setup
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise IOError("Cannot open USB camera")

# Load YOLOv8 Model
model = YOLO("best.pt")

# === Alert Flags ===
email_sent_knife = False
email_sent_gun = False

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        results = model(frame, imgsz=320)
        annotated_frame = results[0].plot()

        # FPS Overlay
        inference_time = results[0].speed["inference"]
        fps = 1000 / inference_time if inference_time > 0 else 0
        text = f"FPS: {fps:.1f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1, 2)[0]
        text_x = annotated_frame.shape[1] - text_size[0] - 10
        text_y = text_size[1] + 10
        cv2.putText(annotated_frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

        # Detection Logic
        detected_classes = [model.names[int(cls)].lower() for cls in results[0].boxes.cls.cpu().numpy()]
        knife_detected = 'knife' in detected_classes
        gun_detected = 'gun' in detected_classes

        # LED Logic
        GPIO.output(LED_PIN, GPIO.HIGH if knife_detected or gun_detected else GPIO.LOW)

        # Alarm Sound Logic
        if (knife_detected or gun_detected) and not alarm_playing:
            alarm_sound.play(-1)
            alarm_playing = True
        elif not knife_detected and not gun_detected and alarm_playing:
            alarm_sound.stop()
            alarm_playing = False

        # Email and Log Logic
        for label in detected_classes:
            if label == 'knife' and not email_sent_knife:
                print("Knife detected!")
                send_email_alert("Knife Detected!", "A knife was detected by your Raspberry Pi.")
                log_event("knife")
                email_sent_knife = True

            elif label == 'gun' and not email_sent_gun:
                print("Gun detected!")
                send_email_alert("Gun Detected!", "A gun was detected by your Raspberry Pi.")
                log_event("gun")
                email_sent_gun = True

        # Display Frame
        cv2.imshow("YOLO Detection", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    print("Exiting detection loop. Cleaning up resources.")
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.cleanup()
    alarm_sound.stop()
    cap.release()
    cv2.destroyAllWindows()