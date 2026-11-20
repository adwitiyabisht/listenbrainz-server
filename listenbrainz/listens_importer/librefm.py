import time

import requests

from flask import current_app

from listenbrainz.domain.external_service import ExternalServiceAPIError, LastfmUserNotRetryableException
from listenbrainz.domain.librefm import LibrefmService
from listenbrainz.listens_importer.lastfm import BaseLastfmImporter
from listenbrainz.webserver import create_app


class LibrefmImporter(BaseLastfmImporter):

    def __init__(self):
        super().__init__(
            name="LibreFmImporter",
            user_friendly_name="Libre.fm",
            service=LibrefmService(),
            api_key=current_app.config["LIBREFM_API_KEY"],
            api_base_url=current_app.config["LIBREFM_API_URL"],
        )

    def get_user_recent_tracks(self, session, user, page):
        time.sleep(1)
        return super().get_user_recent_tracks(session, user, page)

    def handle_no_tracks_error(self, session, user):
        if not self._verify_user_exists(session, user):
            self._remove_missing_user(user)
        return super().handle_no_tracks_error(session, user)

    def handle_recent_tracks_not_found(self, session, user):
        if not self._verify_user_exists(session, user):
            self._remove_missing_user(user)

        raise ExternalServiceAPIError(
            "Libre.fm returned a not-found response for recent tracks for user %s, "
            "but user.getinfo confirms the account exists" % user["external_user_id"]
        )

    def _verify_user_exists(self, session, user):
        username = user["external_user_id"]
        params = {
            "method": "user.getinfo",
            "format": "json",
            "api_key": self.api_key,
            "user": username,
        }

        try:
            response = session.get(self.api_base_url, params=params)
        except requests.exceptions.RequestException as e:
            raise ExternalServiceAPIError("Error while verifying the Libre.fm user: %s" % e)

        if response.status_code == 404:
            return False

        if response.status_code != 200:
            raise ExternalServiceAPIError(
                "Error while verifying the Libre.fm user: %s" % response.text
            )

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            raise ExternalServiceAPIError(
                "Error while verifying the Libre.fm user: %s" % response.text
            )

        if not isinstance(data, dict):
            raise ExternalServiceAPIError("Unexpected Libre.fm user response")

        error = data.get("error")
        if error is not None:
            code = error.get("code") if isinstance(error, dict) else error
            if str(code) == "7":
                return False
            raise ExternalServiceAPIError(
                "Error while verifying the Libre.fm user: %s" % error
            )

        if not isinstance(data.get("user"), dict):
            raise ExternalServiceAPIError("Unexpected Libre.fm user response.")

        return True

    def _remove_missing_user(self, user):
        self.service.remove_user(user["user_id"], remove_import_log=False)
        raise LastfmUserNotRetryableException(
            "Libre.fm user with username %s not found" % user["external_user_id"]
        )

    def get_total_pages(self, session, user):
        response = super().get_user_recent_tracks(session, user, page=1)
        return int(response["recenttracks"]["@attr"]["totalPages"])


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        importer = LibrefmImporter()
        importer.main()
