package api

import (
	"net/http"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type notificationPayload struct {
	ManhwaID int    `json:"manhwa_id"`
	Message  string `json:"message"`
	Read     bool   `json:"read"`
}

func (r *router) listNotifications(w http.ResponseWriter, _ *http.Request) {
	r.store.Mu.RLock()
	items := make([]app.Notification, 0, len(r.store.Notifications))
	for _, n := range r.store.Notifications {
		items = append(items, n)
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) createNotification(w http.ResponseWriter, req *http.Request) {
	var payload notificationPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Message == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	id := r.store.NextNotificationID
	r.store.NextNotificationID++
	item := app.Notification{ID: id, ManhwaID: payload.ManhwaID, Message: payload.Message, Read: payload.Read, CreatedAt: nowUTC()}
	r.store.Notifications[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusCreated, item)
}

func (r *router) getNotification(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	r.store.Mu.RLock()
	item, exists := r.store.Notifications[id]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (r *router) updateNotification(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	var payload notificationPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Message == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	item, exists := r.store.Notifications[id]
	if !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	item.ManhwaID = payload.ManhwaID
	item.Message = payload.Message
	item.Read = payload.Read
	r.store.Notifications[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusOK, item)
}

func (r *router) deleteNotification(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Notifications[id]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	delete(r.store.Notifications, id)
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}
