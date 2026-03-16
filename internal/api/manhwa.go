package api

import (
	"net/http"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

type manhwaPayload struct {
	Title       string `json:"title"`
	Slug        string `json:"slug"`
	Description string `json:"description"`
}

func (r *router) listManhwas(w http.ResponseWriter, _ *http.Request) {
	r.store.Mu.RLock()
	items := make([]app.Manhwa, 0, len(r.store.Manhwas))
	for _, m := range r.store.Manhwas {
		items = append(items, m)
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) createManhwa(w http.ResponseWriter, req *http.Request) {
	var payload manhwaPayload
	if err := decodeJSON(req, &payload); err != nil || payload.Title == "" || payload.Slug == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	id := r.store.NextManhwaID
	r.store.NextManhwaID++
	item := app.Manhwa{ID: id, Title: payload.Title, Slug: payload.Slug, Description: payload.Description, CreatedAt: nowUTC()}
	r.store.Manhwas[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusCreated, item)
}

func (r *router) getManhwa(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	r.store.Mu.RLock()
	item, exists := r.store.Manhwas[id]
	r.store.Mu.RUnlock()
	if !exists {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (r *router) updateManhwa(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	var payload manhwaPayload
	if err := decodeJSON(req, &payload); err != nil || payload.Title == "" || payload.Slug == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid payload"})
		return
	}

	r.store.Mu.Lock()
	item, exists := r.store.Manhwas[id]
	if !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	item.Title = payload.Title
	item.Slug = payload.Slug
	item.Description = payload.Description
	r.store.Manhwas[id] = item
	r.store.Mu.Unlock()
	writeJSON(w, http.StatusOK, item)
}

func (r *router) deleteManhwa(w http.ResponseWriter, req *http.Request) {
	id, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[id]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	delete(r.store.Manhwas, id)
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}

func (r *router) listManhwaChapters(w http.ResponseWriter, req *http.Request) {
	manhwaID, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}

	r.store.Mu.RLock()
	items := make([]app.Chapter, 0)
	for _, chapter := range r.store.Chapters {
		if chapter.ManhwaID == manhwaID {
			items = append(items, chapter)
		}
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}

func (r *router) favoriteManhwa(w http.ResponseWriter, req *http.Request) {
	manhwaID, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	uid := r.userID(req)

	r.store.Mu.Lock()
	if _, exists := r.store.Manhwas[manhwaID]; !exists {
		r.store.Mu.Unlock()
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "manhwa not found"})
		return
	}
	if _, exists := r.store.Favorites[uid]; !exists {
		r.store.Favorites[uid] = map[int]bool{}
	}
	r.store.Favorites[uid][manhwaID] = true
	r.store.Mu.Unlock()

	writeJSON(w, http.StatusOK, map[string]any{"favorite": true, "manhwa_id": manhwaID})
}

func (r *router) unfavoriteManhwa(w http.ResponseWriter, req *http.Request) {
	manhwaID, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	uid := r.userID(req)

	r.store.Mu.Lock()
	if Favorites, exists := r.store.Favorites[uid]; exists {
		delete(Favorites, manhwaID)
	}
	r.store.Mu.Unlock()
	w.WriteHeader(http.StatusNoContent)
}

func (r *router) isFavorite(w http.ResponseWriter, req *http.Request) {
	manhwaID, ok := parseID(req, "id")
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid id"})
		return
	}
	uid := r.userID(req)

	r.store.Mu.RLock()
	favorite := r.store.Favorites[uid][manhwaID]
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, map[string]any{"favorite": favorite, "manhwa_id": manhwaID})
}

func (r *router) listFavorites(w http.ResponseWriter, req *http.Request) {
	uid := r.userID(req)

	r.store.Mu.RLock()
	ids := r.store.Favorites[uid]
	items := make([]app.Manhwa, 0, len(ids))
	for id := range ids {
		if m, exists := r.store.Manhwas[id]; exists {
			items = append(items, m)
		}
	}
	r.store.Mu.RUnlock()
	writeJSON(w, http.StatusOK, items)
}
