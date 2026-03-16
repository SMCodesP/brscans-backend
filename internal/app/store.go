package app

import (
	"crypto/rand"
	"encoding/hex"
	"sync"
	"time"
)

type Manhwa struct {
	ID          int       `json:"id"`
	Title       string    `json:"title"`
	Slug        string    `json:"slug"`
	Description string    `json:"description,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
}

type Chapter struct {
	ID        int       `json:"id"`
	ManhwaID  int       `json:"manhwa_id"`
	Number    int       `json:"number"`
	Title     string    `json:"title"`
	CreatedAt time.Time `json:"created_at"`
}

type ImageVariant struct {
	ID        int       `json:"id"`
	ChapterID int       `json:"chapter_id"`
	URL       string    `json:"url"`
	Variant   string    `json:"variant"`
	CreatedAt time.Time `json:"created_at"`
}

type Comment struct {
	ID        int       `json:"id"`
	ManhwaID  int       `json:"manhwa_id"`
	Author    string    `json:"author"`
	Content   string    `json:"content"`
	CreatedAt time.Time `json:"created_at"`
}

type Notification struct {
	ID        int       `json:"id"`
	ManhwaID  int       `json:"manhwa_id"`
	Message   string    `json:"message"`
	Read      bool      `json:"read"`
	CreatedAt time.Time `json:"created_at"`
}

type User struct {
	ID       int    `json:"id"`
	Username string `json:"username"`
	Password string `json:"-"`
}

type Store struct {
	Mu sync.RWMutex

	Manhwas       map[int]Manhwa
	Chapters      map[int]Chapter
	Images        map[int]ImageVariant
	Comments      map[int]Comment
	Notifications map[int]Notification
	Users         map[int]User

	Sessions  map[string]int
	Favorites map[int]map[int]bool

	NextManhwaID       int
	NextChapterID      int
	NextImageID        int
	NextCommentID      int
	NextNotificationID int
	NextUserID         int
}

func NewStore() *Store {
	return &Store{
		Manhwas:            map[int]Manhwa{},
		Chapters:           map[int]Chapter{},
		Images:             map[int]ImageVariant{},
		Comments:           map[int]Comment{},
		Notifications:      map[int]Notification{},
		Users:              map[int]User{},
		Sessions:           map[string]int{},
		Favorites:          map[int]map[int]bool{},
		NextManhwaID:       1,
		NextChapterID:      1,
		NextImageID:        1,
		NextCommentID:      1,
		NextNotificationID: 1,
		NextUserID:         1,
	}
}

func NewSessionToken() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return time.Now().UTC().Format("20060102150405.000000000")
	}
	return hex.EncodeToString(b)
}
