package api

import (
	"net/http"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type imagePayload struct {
	ChapterID int    `json:"chapter_id"`
	URL       string `json:"url"`
	Variant   string `json:"variant"`
}

func (r *router) listImages(w http.ResponseWriter, _ *http.Request) {
	r.store.Mu.RLock()
	items := make([]app.ImageVariant, 0, len(r.store.Images))
	for _, image := range r.store.Images {
		items = append(items, image)
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) createImage(w http.ResponseWriter, req *http.Request) {
	var payload imagePayload
	if err := decodeJSON(req, &payload); err != nil || payload.ChapterID <= 0 || payload.URL == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Chapters[payload.ChapterID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "chapter not found"})
		return
	}
	id := r.store.NextImageID
	r.store.NextImageID++
	item := app.ImageVariant{ID: id, ChapterID: payload.ChapterID, URL: payload.URL, Variant: payload.Variant, CreatedAt: nowUTC()}
	r.store.Images[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusCreated, item)
}

func (r *router) getImage(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	r.store.Mu.RLock()
	item, exists := r.store.Images[id]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (r *router) updateImage(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	var payload imagePayload
	if err := decodeJSON(req, &payload); err != nil || payload.ChapterID <= 0 || payload.URL == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Chapters[payload.ChapterID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "chapter not found"})
		return
	}
	item, exists := r.store.Images[id]
	if !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	item.ChapterID = payload.ChapterID
	item.URL = payload.URL
	item.Variant = payload.Variant
	r.store.Images[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusOK, item)
}

func (r *router) deleteImage(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Images[id]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	delete(r.store.Images, id)
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}
