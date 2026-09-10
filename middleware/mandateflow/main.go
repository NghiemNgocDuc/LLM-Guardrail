// MandateFlow Go sidecar — fast provenance gateway.
// Port of Python app/services/mandate_service.py + mandate_fixtures.py
// onto Go + SQLite WAL (single-connection, _txlock=immediate, busy_timeout=5000)
// as in the original MandateFlow demo. Python remains fallback.
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const (
	pinnedRuleID  = "NO_PAYMENT_REIDENTIFICATION"
	pinnedReason  = "Payment-derived references are aggregate-only and cannot be resolved through CRM"
	supportDerived       = "SUPPORT_DERIVED"
	paymentAggregateOnly = "PAYMENT_AGGREGATE_ONLY"
)

var db *sql.DB

func hashCap(raw string) string {
	h := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(h[:])
}

func constantTimeEq(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

func attenuate(parent, requested []string) []string {
	if len(requested) == 0 {
		return parent
	}
	if len(parent) == 0 {
		return requested
	}
	pm := map[string]bool{}
	for _, v := range parent {
		pm[v] = true
	}
	var out []string
	for _, v := range requested {
		if pm[v] {
			out = append(out, v)
		}
	}
	return out
}

func evaluatePinnedPolicy(tool, provenance string) (string, *string, *string) {
	if tool == "crm.resolve_customer" && provenance == paymentAggregateOnly {
		rid := pinnedRuleID
		rsn := pinnedReason
		return "DENY", &rid, &rsn
	}
	return "ALLOW", nil, nil
}

func provenanceForHandle(handle string) string {
	if handle == "" {
		return ""
	}
	var prov string
	err := db.QueryRow("SELECT provenance FROM provenance_references WHERE handle = ?", handle).Scan(&prov)
	if err != nil {
		return ""
	}
	// walk ancestry — if any parent is PAYMENT_AGGREGATE_ONLY, taint persists
	cur := handle
	for cur != "" {
		var p, parentID sql.NullString
		var curProv string
		err := db.QueryRow("SELECT provenance, parent_id FROM provenance_references WHERE handle = ?", cur).Scan(&curProv, &parentID)
		if err != nil {
			break
		}
		if curProv == paymentAggregateOnly {
			return paymentAggregateOnly
		}
		if parentID.Valid && parentID.String != "" {
			// need handle of parent
			var ph string
			_ = db.QueryRow("SELECT handle FROM provenance_references WHERE id = ?", parentID.String).Scan(&ph)
			cur = ph
			_ = p
		} else {
			break
		}
	}
	return prov
}

func initDB() {
	path := os.Getenv("MANDATEFLOW_DB")
	if path == "" {
		path = "./mandateflow.db"
	}
	// WAL + immediate tx lock + FKs — same as MandateFlow Go sidecar
	dsn := fmt.Sprintf("file:%s?_txlock=immediate&_busy_timeout=5000&_journal_mode=WAL&_foreign_keys=ON", path)
	var err error
	db, err = sql.Open("sqlite3", dsn)
	if err != nil {
		log.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	schema := `
	CREATE TABLE IF NOT EXISTS mandates (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, owner_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', policy_context TEXT NOT NULL DEFAULT '{}', expires_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL);
	CREATE TABLE IF NOT EXISTS capabilities (id TEXT PRIMARY KEY, mandate_id TEXT NOT NULL, run_id TEXT, capability_hash TEXT NOT NULL, scopes TEXT NOT NULL DEFAULT '[]', expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
	CREATE INDEX IF NOT EXISTS ix_cap_hash ON capabilities(capability_hash);
	CREATE TABLE IF NOT EXISTS provenance_references (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, owner_id TEXT NOT NULL, kind TEXT NOT NULL, provenance TEXT NOT NULL, parent_id TEXT, handle TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
	CREATE TABLE IF NOT EXISTS mandate_runs (id TEXT PRIMARY KEY, mandate_id TEXT NOT NULL, org_id TEXT NOT NULL, capability_id TEXT, status TEXT NOT NULL DEFAULT 'pending', runtime_id TEXT, correlation_id TEXT, created_at TEXT NOT NULL, completed_at TEXT);
	CREATE TABLE IF NOT EXISTS mandate_receipts (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, mandate_id TEXT NOT NULL, org_id TEXT NOT NULL, tool TEXT NOT NULL, decision TEXT NOT NULL, rule_id TEXT, reason TEXT, provenance_at_call TEXT, latency_ms INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
	CREATE TABLE IF NOT EXISTS fixture_counters (org_id TEXT NOT NULL, fixture TEXT NOT NULL, counter INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY (org_id, fixture));
	`
	for _, stmt := range strings.Split(schema, ";") {
		stmt = strings.TrimSpace(stmt)
		if stmt == "" {
			continue
		}
		if _, err := db.Exec(stmt); err != nil {
			log.Fatalf("migrate: %v stmt %q", err, stmt)
		}
	}
}

func withCORS(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
}

func jsonError(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]any{"detail": msg})
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	withCORS(w)
	if r.Header.Get("Origin") != "" {
		http.Error(w, "Origin not allowed", 403)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "engine": "go", "db": "sqlite-wal"})
}

func handleCall(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Origin") != "" {
		http.Error(w, "Origin not allowed", 403)
		return
	}
	withCORS(w)
	if r.Method == "OPTIONS" {
		w.WriteHeader(204)
		return
	}
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		http.Error(w, "Missing Bearer capability", 401)
		return
	}
	raw := strings.TrimPrefix(auth, "Bearer ")
	raw = strings.TrimSpace(raw)
	h := hashCap(raw)

	start := time.Now()
	var capID, mandateID, runID, orgID, expiresAt, scopesJSON string
	// constant-time scan over non-expired caps
	rows, err := db.Query("SELECT id, mandate_id, run_id, capability_hash, scopes, expires_at FROM capabilities WHERE datetime(expires_at) > datetime('now')")
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer rows.Close()
	found := false
	for rows.Next() {
		var h2 string
		var id, mid, rid sql.NullString
		var sc, exp string
		if err := rows.Scan(&id, &mid, &rid, &h2, &sc, &exp); err != nil {
			continue
		}
		// use hmac.Equal style constant-time
		if hmac.Equal([]byte(h), []byte(h2)) && subtle.ConstantTimeCompare([]byte(h), []byte(h2)) == 1 && constantTimeEq(h, h2) {
			capID = id.String
			mandateID = mid.String
			if rid.Valid {
				runID = rid.String
			}
			scopesJSON = sc
			expiresAt = exp
			_ = orgID
			found = true
			break
		}
	}
	if !found {
		http.Error(w, "Invalid or expired capability", 401)
		return
	}
	// check mandate still active
	var mStatus string
	if err := db.QueryRow("SELECT status, org_id FROM mandates WHERE id = ?", mandateID).Scan(&mStatus, &orgID); err != nil || mStatus != "active" {
		http.Error(w, "Mandate revoked", 403)
		return
	}
	var body struct {
		Tool   string         `json:"tool"`
		Handle string         `json:"handle"`
		Inputs map[string]any `json:"inputs"`
		RunID  string         `json:"run_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "bad json", 400)
		return
	}
	if runID == "" && body.RunID != "" {
		runID = body.RunID
	}
	// scope check
	if scopesJSON != "" && scopesJSON != "[]" {
		var scopes []string
		_ = json.Unmarshal([]byte(scopesJSON), &scopes)
		allowed := false
		for _, s := range scopes {
			if s == body.Tool || s == "*" {
				allowed = true
				break
			}
		}
		if !allowed && len(scopes) > 0 {
			lat := int(time.Since(start).Milliseconds())
			id := fmt.Sprintf("rcpt_%d", time.Now().UnixNano())
			rule := "SCOPE_DENIED"
			reason := fmt.Sprintf("Tool %s not in capability scope %v", body.Tool, scopes)
			_, _ = db.Exec("INSERT INTO mandate_receipts (id, run_id, mandate_id, org_id, tool, decision, rule_id, reason, provenance_at_call, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
				id, runID, mandateID, orgID, body.Tool, "DENY", rule, reason, "", lat)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"decision": "DENY", "ruleId": rule, "reason": reason, "receipt_id": id, "tool": body.Tool})
			_ = scopesJSON
			_ = expiresAt
			return
		}
	}
	prov := provenanceForHandle(body.Handle)
	decision, ruleID, reason := evaluatePinnedPolicy(body.Tool, prov)
	lat := int(time.Since(start).Milliseconds())
	receiptID := fmt.Sprintf("rcpt_%d", time.Now().UnixNano())
	var ruleStr, reasonStr sql.NullString
	if ruleID != nil {
		ruleStr = sql.NullString{String: *ruleID, Valid: true}
	}
	if reason != nil {
		reasonStr = sql.NullString{String: *reason, Valid: true}
	}
	tx, _ := db.Begin()
	_, _ = tx.Exec("INSERT INTO mandate_receipts (id, run_id, mandate_id, org_id, tool, decision, rule_id, reason, provenance_at_call, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
		receiptID, runID, mandateID, orgID, body.Tool, decision, ruleStr.String, reasonStr.String, prov, lat)
	if decision == "DENY" {
		_ = tx.Commit()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"decision": "DENY", "ruleId": ruleStr.String, "reason": reasonStr.String, "receipt_id": receiptID, "tool": body.Tool})
		return
	}
	// ALLOW → increment fixture_counters in same tx (WAL immediate)
	_, _ = tx.Exec("INSERT INTO fixture_counters (org_id, fixture, counter, updated_at) VALUES (?,?,1,datetime('now')) ON CONFLICT(org_id, fixture) DO UPDATE SET counter=counter+1, updated_at=datetime('now')", orgID, body.Tool)
	var cnt int
	_ = tx.QueryRow("SELECT counter FROM fixture_counters WHERE org_id=? AND fixture=?", orgID, body.Tool).Scan(&cnt)
	_ = tx.Commit()
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"decision": "ALLOW", "receipt_id": receiptID, "tool": body.Tool, "result": map[string]any{"counter": cnt, "crmCounter": cnt}})
	_ = capID
}

func main() {
	initDB()
	port := os.Getenv("PORT")
	if port == "" {
		port = "8182"
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/gateway/call", handleCall)
	mux.HandleFunc("/call", handleCall) // alias
	addr := ":" + port
	log.Printf("mandateflow go sidecar listening on %s db=%s", addr, os.Getenv("MANDATEFLOW_DB"))
	log.Fatal(http.ListenAndServe(addr, mux))
}
