from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from django_metronome.client import MetronomeClientDisabledError
from django_metronome.conf import get_metronome_settings
from django_metronome.services import MetronomeAdapter


def hello(request):
    return HttpResponse("Hello, world")


@require_http_methods(["POST"])
def sync_customer(request: HttpRequest, customer_id: str) -> JsonResponse:
    settings = get_metronome_settings()
    if not settings.is_enabled:
        return JsonResponse(
            {"detail": "Metronome integration disabled; configure METRONOME_API_KEY."},
            status=503,
        )

    try:
        adapter = MetronomeAdapter()
        payload = adapter.retrieve_customer(customer_id)
    except MetronomeClientDisabledError:
        return JsonResponse(
            {"detail": "Metronome client is not configured."}, status=503
        )

    return JsonResponse(
        {
            "status": "ok",
            "customer_id": payload.get("id"),
            "environment": settings.environment,
            "payload": payload,
        }
    )
