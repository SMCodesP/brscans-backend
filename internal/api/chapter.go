package api

import (
	"net/http"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type chapterPayload struct {
	ManhwaID int    `json:"manhwa_id"`
	Number   int    `json:"number"`
	Title    string `json:"title"`
}

func (r *router) listChapters(w http.ResponseWriter, _ *http.Request) {
	r.store.Mu.RLock()
	items := make([]app.Chapter, 0, len(r.store.Chapters))
	for _, chapter := range r.store.Chapters {
		items = append(items, chapter)
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) createChapter(w http.ResponseWriter, req *http.Request) {
	var payload chapterPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Title == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	id := r.store.NextChapterID
	r.store.NextChapterID++
	item := app.Chapter{ID: id, ManhwaID: payload.ManhwaID, Number: payload.Number, Title: payload.Title, CreatedAt: nowUTC()}
	r.store.Chapters[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusCreated, item)
}

func (r *router) getChapter(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	r.store.Mu.RLock()
	item, exists := r.store.Chapters[id]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (r *router) updateChapter(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	var payload chapterPayload
	if err := decodeJSON(req, &payload); err != nil || payload.ManhwaID <= 0 || payload.Title == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[payload.ManhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	item, exists := r.store.Chapters[id]
	if !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	item.ManhwaID = payload.ManhwaID
	item.Number = payload.Number
	item.Title = payload.Title
	r.store.Chapters[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusOK, item)
}

func (r *router) deleteChapter(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Chapters[id]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	delete(r.store.Chapters, id)
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}
