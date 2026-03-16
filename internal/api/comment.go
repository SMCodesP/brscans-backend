package api

import (
	"net/http"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type commentPayload struct {
	ManhwaID int    `json:"manhwa_id"`
	Author   string `json:"author"`
	Content  string `json:"content"`
}

func (r *router) listComments(w http.ResponseWriter, _ *http.Request) {
	r.store.Mu.RLock()
	items := make([]app.Comment, 0, len(r.store.Comments))
	for _, comment := range r.store.Comments {
		items = append(items, comment)
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) createComment(w http.ResponseWriter, req *http.Request) {
	var payload commentPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Content == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	id := r.store.NextCommentID
	r.store.NextCommentID++
	item := app.Comment{ID: id, ManhwaID: payload.ManhwaID, Author: payload.Author, Content: payload.Content, CreatedAt: nowUTC()}
	r.store.Comments[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusCreated, item)
}

func (r *router) getComment(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	r.store.Mu.RLock()
	item, exists := r.store.Comments[id]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (r *router) updateComment(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	var payload commentPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Content == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	item, exists := r.store.Comments[id]
	if !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	item.ManhwaID = payload.ManhwaID
	item.Author = payload.Author
	item.Content = payload.Content
	r.store.Comments[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusOK, item)
}

func (r *router) deleteComment(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Comments[id]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	delete(r.store.Comments, id)
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}
