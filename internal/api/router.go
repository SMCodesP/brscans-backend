package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type router struct {
	store *app.Store
}

func NewRouter(store *app.Store) http.Handler {
	r := &router{store: store}
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", r.healthz)
	mux.HandleFunc("GET /wrapper", r.wrapper)
	mux.HandleFunc("GET /api/schema/", r.schema)
	mux.HandleFunc("GET /api/swagger/", r.swagger)
	mux.HandleFunc("GET /api/redoc/", r.redoc)

	mux.HandleFunc("GET /manhwas", r.listManhwas)
	mux.HandleFunc("POST /manhwas", r.createManhwa)
	mux.HandleFunc("GET /manhwas/{id}", r.getManhwa)
	mux.HandleFunc("PUT /manhwas/{id}", r.updateManhwa)
	mux.HandleFunc("DELETE /manhwas/{id}", r.deleteManhwa)
	mux.HandleFunc("GET /manhwas/{id}/chapters", r.listManhwaChapters)
	mux.HandleFunc("POST /manhwas/{id}/favorite", r.favoriteManhwa)
	mux.HandleFunc("DELETE /manhwas/{id}/favorite", r.unfavoriteManhwa)
	mux.HandleFunc("GET /manhwas/{id}/is-favorite", r.isFavorite)
	mux.HandleFunc("GET /favorites", r.listFavorites)

	mux.HandleFunc("GET /chapters", r.listChapters)
	mux.HandleFunc("POST /chapters", r.createChapter)
	mux.HandleFunc("GET /chapters/{id}", r.getChapter)
	mux.HandleFunc("PUT /chapters/{id}", r.updateChapter)
	mux.HandleFunc("DELETE /chapters/{id}", r.deleteChapter)

	mux.HandleFunc("GET /images", r.listImages)
	mux.HandleFunc("POST /images", r.createImage)
	mux.HandleFunc("GET /images/{id}", r.getImage)
	mux.HandleFunc("PUT /images/{id}", r.updateImage)
	mux.HandleFunc("DELETE /images/{id}", r.deleteImage)

	mux.HandleFunc("GET /comments", r.listComments)
	mux.HandleFunc("POST /comments", r.createComment)
	mux.HandleFunc("GET /comments/{id}", r.getComment)
	mux.HandleFunc("PUT /comments/{id}", r.updateComment)
	mux.HandleFunc("DELETE /comments/{id}", r.deleteComment)

	mux.HandleFunc("GET /notifications", r.listNotifications)
	mux.HandleFunc("POST /notifications", r.createNotification)
	mux.HandleFunc("GET /notifications/{id}", r.getNotification)
	mux.HandleFunc("PUT /notifications/{id}", r.updateNotification)
	mux.HandleFunc("DELETE /notifications/{id}", r.deleteNotification)

	mux.HandleFunc("POST /auth/register", r.register)
	mux.HandleFunc("POST /auth/login", r.login)
	mux.HandleFunc("GET /auth/me", r.me)
	mux.HandleFunc("POST /auth/discord", r.discordAuth)

	return mux
}

func (r *router) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "brscans-backend-go"})
}

func (r *router) wrapper(w http.ResponseWriter, req *http.Request) {
	url := req.URL.Query().Get("url")
	writeJSON(w, http.StatusOK, map[string]any{
		"url":        url,
		"normalized": strings.TrimSpace(url),
		"status":     "received",
	})
}

func (r *router) schema(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"openapi": "3.0.0",
		"info": map[string]string{
			"title":   "Brscans Backend API",
			"version": "v1",
		},
	})
}

func (r *router) swagger(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"message": "Swagger UI not embedded in this build. Use /api/schema/."})
}

func (r *router) redoc(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"message": "ReDoc UI not embedded in this build. Use /api/schema/."})
}

func parseID(req *http.Request, key string) (int, bool) {
	id, err := strconv.Atoi(req.PathValue(key))
	if err != nil || id <= 0 {
		return 0, false
	}
	return id, true
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func decodeJSON(req *http.Request, target any) error {
	return json.NewDecoder(req.Body).Decode(target)
}

func (r *router) userID(req *http.Request) int {
	token := req.Header.Get("Authorization")
	if strings.HasPrefix(strings.ToLower(token), "bearer ") {
		token = strings.TrimSpace(token[7:])
		r.store.Mu.RLock()
		uid := r.store.Sessions[token]
		r.store.Mu.RUnlock()
		if uid > 0 {
			return uid
		}
	}
	if raw := strings.TrimSpace(req.Header.Get("X-User-ID")); raw != "" {
		if id, err := strconv.Atoi(raw); err == nil && id > 0 {
			return id
		}
	}
	return 1
}

func nowUTC() time.Time {
	return time.Now().UTC()
}
