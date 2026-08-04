from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .forms import TelegramMessageForm
from .libs.telegram_api import send_telegram_message


@login_required
def send_message_view(request):
    """Seite zum manuellen Versenden einer Telegram-Nachricht. Login erforderlich."""
    if request.method == 'POST':
        if request.POST.get('action') == 'cancel':
            return redirect('homepage:index')

        form = TelegramMessageForm(request.POST)
        text = (request.POST.get('message') or '').strip()

        if not text:
            messages.warning(request, 'Bitte eine Nachricht eingeben.')
            return render(request, 'telegram_app/send_message.html', {'form': form})

        if send_telegram_message(text):
            messages.success(request, 'Nachricht wurde per Telegram versendet.')
        else:
            messages.error(request, 'Telegram-Versand fehlgeschlagen. Bitte später erneut versuchen.')
            return render(request, 'telegram_app/send_message.html', {'form': form})

        # Erfolg: Feld leeren, auf der Seite bleiben
        form = TelegramMessageForm()
    else:
        form = TelegramMessageForm()

    return render(request, 'telegram_app/send_message.html', {'form': form})
