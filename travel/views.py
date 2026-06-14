import json
import logging
import airportsdata

from django.shortcuts import render
from django.http import JsonResponse
from .forms import FlightSearchForm
from .services.serpapi_client import search_flights, fetch_return_flights

_airports = airportsdata.load('IATA')

logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'travel/index.html')


def flight_search(request):
    form = FlightSearchForm(request.GET or None)
    results = None
    error = None

    if request.GET and form.is_valid():
        cd = form.cleaned_data
        try:
            results = search_flights(
                departure_id=cd['departure_airport'],
                arrival_id=cd['arrival_airport'],
                outbound_date=cd['outbound_date'],
                return_date=cd.get('return_date'),
                adults=cd['adults'],
                travel_class=cd['travel_class'],
                direct_only=cd['direct_only'],
            )
        except ValueError as e:
            error = str(e)
        except Exception as e:
            logger.exception('Flugsuche fehlgeschlagen')
            error = f'Suche fehlgeschlagen: {e}'

    return render(request, 'travel/flight_search.html', {
        'form': form,
        'results': results,
        'error': error,
    })


def airport_lookup(request):
    code = request.GET.get('code', '').strip().upper()
    if len(code) != 3:
        return JsonResponse({'error': 'Ungültiger Code.'}, status=400)
    ap = _airports.get(code)
    if not ap:
        return JsonResponse({'error': 'Flughafen nicht gefunden.'}, status=404)
    return JsonResponse({
        'name': ap['name'],
        'city': ap['city'],
        'country': ap['country'],
    })


def return_flights_ajax(request):
    token = request.GET.get('token', '').strip()
    if not token:
        return JsonResponse({'error': 'Kein Token angegeben.'}, status=400)

    base_params = {k: v for k, v in request.GET.items() if k != 'token'}

    try:
        return_options = fetch_return_flights(token, base_params)
        return JsonResponse({'return_options': return_options})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception('Return-flight AJAX fehlgeschlagen')
        return JsonResponse({'error': str(e)}, status=500)
