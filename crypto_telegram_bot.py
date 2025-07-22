import requests
import os

def send_message_telegram(message):
    bot_token = os.environ.get("TELEGRAM_SECRET_TOKEN")
    bot_chatid = '-1001588052001'

    send_text = 'https://api.telegram.org/bot'+bot_token+'/sendMessage?chat_id='+bot_chatid+'&text='+message

    response = requests.get(send_text)

def send_file_telegram(message):
    bot_token = os.environ.get("TELEGRAM_SECRET_TOKEN")
    bot_chatid = '-1001588052001'

    a = open(message, 'rb')
    send_document = 'https://api.telegram.org/bot' + bot_token + '/sendDocument?'
    data = {
        'chat_id': bot_chatid,
        'parse_mode': 'HTML',
    }

    requests.post(send_document, data=data, files={'document': a},stream=True)
