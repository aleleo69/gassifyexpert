# Biomass Gasifier - Porting IONOS

Questo pacchetto e' pensato per un hosting IONOS con supporto CGI Python.
Non richiede Flask, Django o librerie esterne.

## Struttura

```text
public_html/index.html              Interfaccia web
public_html/robots.txt              Blocco indicizzazione crawler
public_html/.htaccess               Abilitazione handler CGI su Apache/IONOS
public_html/cgi-bin/health.cgi      Diagnostica Python CGI
public_html/cgi-bin/simulate.cgi    API di simulazione
public_html/cgi-bin/download.cgi    Download JSON/CSV
public_html/app/*.py                Motore di calcolo Python
public_html/logs/access.jsonl       Registro chiamate JSON Lines
public_html/logs/counter.txt        Contatore persistente
public_html/logs/.htaccess          Blocco accesso HTTP ai log
```

## Caricamento su IONOS

1. Carica tutto il contenuto di `public_html` nella document root del sito.
   Devono risultare affiancati `index.html`, `robots.txt`, `cgi-bin` e `app`.
2. In alternativa, carica l'intera cartella `public_html` e configura il
   sottodominio affinche punti esattamente a quella cartella.
3. Non separare `cgi-bin` e `app`: l'interfaccia usa gli URL
   `/cgi-bin/simulate.cgi` e `/cgi-bin/download.cgi`.
4. Imposta permessi eseguibili sugli script CGI:

```bash
chmod 755 public_html/cgi-bin/health.cgi
chmod 755 public_html/cgi-bin/simulate.cgi
chmod 755 public_html/cgi-bin/download.cgi
chmod 750 public_html/logs
chmod 660 public_html/logs/access.jsonl
chmod 660 public_html/logs/counter.txt
```

5. Verifica che la prima riga degli script punti a Python 3:

```text
#!/usr/bin/env python3
```

Se su IONOS il path e' diverso, sostituiscilo, ad esempio:

```text
#!/usr/bin/python3
```

## Test rapido

Apri:

```text
https://tuo-dominio.it/
```

La pagina deve simulare automaticamente il caso esempio. Se lo stato mostra
errore, prova direttamente:

```text
https://tuo-dominio.it/cgi-bin/health.cgi
https://tuo-dominio.it/cgi-bin/simulate.cgi
```

`health.cgi` deve mostrare un piccolo oggetto JSON con `"ok": true`. Se mostra
la pagina HTML del sito, il sottodominio non punta alla cartella `public_html`
corretta o `.htaccess` non e' stato caricato. Se mostra errore 403, controlla
i permessi `755`. Se mostra errore 500, verifica il percorso Python nella prima
riga dello script e consulta i log del webspace.

## Nota su piani IONOS

Alcuni piani hosting condivisi non abilitano Python CGI o lo limitano. In quel
caso usa un VPS/Cloud IONOS e avvia la versione server:

```bash
python3 web_server.py --host 0.0.0.0 --port 8765
```

poi configura Apache/Nginx come reverse proxy verso `127.0.0.1:8765`.

## Sicurezza minima consigliata

- Proteggi la pagina con autenticazione HTTP se e' destinata a uso interno.
- La cartella `logs` contiene indirizzi IP e non deve essere pubblicamente
  accessibile. Il file `.htaccess` incluso applica `Require all denied`.
- Definisci una durata di conservazione, informa gli utenti e tratta gli IP
  secondo la normativa privacy applicabile. Scarica i log via SFTP/SSH o
  Webspace Explorer, non tramite URL pubblico.
- Non usare il modello per compliance o permitting senza calibrazione.
- Limita dimensione richieste POST se esponi il servizio pubblicamente.
