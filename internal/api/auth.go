package api

import (
	"net/http"
	"strings"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type registerPayload struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

func (r *router) register(w http.ResponseWriter, req *http.Request) {
	var payload registerPayload
	if err := decodeJSON(req, &payload); err != nil || strings.TrimSpace(payload.Username) == "" || payload.Password == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	for _, user := range r.store.Users {
		if strings.EqualFold(user.Username, payload.Username) {
			r.store.Mu.Unlock()
			writeJSON(w, http.StatusConflict, map[string]string{"error": "username already exists"})
			return
		}
	}

	id := r.store.NextUserID
	r.store.NextUserID++
	user := app.User{ID: id, Username: strings.TrimSpace(payload.Username), Password: payload.Password}
	r.store.Users[id] = user
	r.store.Mu.Unlock()

	writeJSON(w, http.StatusCreated, map[string]any{"id": user.ID, "username": user.Username})
}

func (r *router) login(w http.ResponseWriter, req *http.Request) {
	var payload registerPayload
	if err := decodeJSON(req, &payload); err != nil || strings.TrimSpace(payload.Username) == "" || payload.Password == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	defer r.store.Mu.Unlock()
	for _, user := range r.store.Users {
		if strings.EqualFold(user.Username, payload.Username) && user.Password == payload.Password {
			token := app.NewSessionToken()
			r.store.Sessions[token] = user.ID
			writeJSON(w, http.StatusOK, map[string]any{"token": token, "user_id": user.ID, "username": user.Username})
			return
		}
	}

	writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid credentials"})
}

func (r *router) me(w http.ResponseWriter, req *http.Request) {
	uid := r.userID(req)
	if uid <= 0 {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	r.store.Mu.RLock()
	user, exists := r.store.Users[uid]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "user not found"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"id": user.ID, "username": user.Username})
}

func (r *router) discordAuth(w http.ResponseWriter, req *http.Request) {
	var payload map[string]any
	if err := decodeJSON(req, &payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "accepted", "provider": "discord", "payload": payload})
}
