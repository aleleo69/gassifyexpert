# Algorithm Notes

This simulator is a screening model. It enforces elemental accounting but uses
transparent semi-empirical closures for product quality.

## Feedstock atoms

Dry feedstock percentages `C, H, N, O, Cl, S, ash/inerts` are converted to
atomic kmol/h. Moisture and optional steam add inlet `H` and `O`. Air adds
`O2` and `N2`.

## Stoichiometric oxygen

Complete-combustion oxygen demand is:

```text
O2_stoich = C + H/4 + S - O/2
```

where `C, H, O, S` are atomic kmol/h. For air gasification:

```text
O2_in = ER * O2_stoich
N2_in = 3.76 * O2_in
```

## Feedstock HHV/PCS

When measured PCS/HHV is not supplied, the tool uses the
Channiwala-Parikh ultimate-analysis correlation, commonly cited for solid
fuels and used in biomass gasification references:

```text
HHV [MJ/kg dry] =
  0.3491*C + 1.1783*H + 0.1005*S
  - 0.1034*O - 0.0151*N - 0.0211*Ash
```

where `C, H, O, N, S, Ash` are dry-basis mass percentages. A Dulong HHV is also
reported for comparison. PCI/LHV is estimated from HHV by subtracting the water
of combustion from fuel hydrogen when no measured PCI is supplied.

## Air requirement

Stoichiometric air is calculated from the same complete-combustion oxygen
demand:

```text
Air_stoich [kmol/h] = O2_stoich * (1 + 3.76)
Air_gasification = ER * Air_stoich
```

The UI reports both kg/h and Nm3/h, plus kg air per kg dry feed.

## Product distribution

The selected model produces target carbon partitions:

- char carbon
- tar carbon, represented as pseudo-tar `C6H6`
- gas carbon split among `CO, CO2, CH4, C2H4, C2H6`

The product builder then closes atom balances using `H2O`, `H2`, `N2`, and
residual `O2` as balancing species. This is why the balance report is more
reliable than any individual empirical coefficient.

## Pollutants and PCDD/F

Sulfur is split mainly between `H2S` and `SO2` as a function of ER. Chlorine is
split mainly between `HCl` and `Cl2`. Fuel nitrogen is split coarsely among
`NH3, HCN, NO, NO2, N2O, N2`.

Dioxins/furans are not predicted as rigorous concentrations. The model reports:

- qualitative risk: low, medium, high
- risk index from 0 to 1
- broad indicative screening ranges for `PCDD/F TEQ` and total `PCDD/F`

The index increases with chlorine, oxygen availability, residual carbon, and
the assumed 200-450 C cooling-window risk. Replace this with plant-specific
sampling, kinetic data, or literature correlations before using it for design
or compliance.

## Char composition

Char mass is closed as:

```text
char = fixed carbon + organic carbon non-IPA + IPA/PAH + ash/inerts
```

The carbon split depends on thermal severity. Higher temperature, ER, and
residence time reduce organic carbon and IPA/PAH indicators. The char output is
a screening composition, not a substitute for proximate analysis, ultimate
analysis, TGA, TOC, or GC-MS measurements.
## Bilancio energetico e recupero termico

La CGE resta definita sulla base PCI:

`CGE = potenza chimica syngas / potenza chimica feedstock`

Il regime puo essere autotermico, con apporto termico esterno nullo, oppure
allotermico, con una potenza termica esterna specificata dall'utente. Il calore
sensibile disponibile raffreddando il syngas umido dalla temperatura del
gassificatore alla temperatura finale impostata e stimato con capacita termiche
medie costanti per specie. Il recupero utile e:

`Q_recuperato = efficacia_scambiatore * Q_sensibile_disponibile`

L'efficienza complessiva richiesta e:

`overall = (potenza chimica syngas + Q_recuperato) / (potenza chimica feedstock + potenza termica esterna)`

Il calcolo non comprende calore latente di condensazione, dispersioni, consumi
elettrici o ausiliari. Per il dimensionamento termico occorrono Cp dipendenti
dalla temperatura e un modello dello scambiatore calibrato.
## Catalizzatori e materiali di letto

Il modello opzionale include olivina, olivina calcinata, calcare, dolomite e
catalizzatore a base nichel. L'effetto e calcolato da tipo, rapporto
catalizzatore/biomassa, attivita relativa, temperatura e rapporto vapore/
biomassa. La severita risultante modifica in modo conservativo:

- conversione del tar verso gas;
- conversione secondaria di una piccola quota di char;
- reforming di CH4, C2H4 e C2H6;
- ripartizione del carbonio riformato tra CO e CO2.

Il catalizzatore e considerato inventario circolante del letto: massa,
calcinazione/carbonatazione, attrito, make-up e disattivazione nel tempo non
entrano nel bilancio di massa. I coefficienti in `catalysts.py` sono
placeholder modificabili e devono essere calibrati con prove sul reattore.
Per ogni caso catalitico il tool esegue anche il caso equivalente senza
catalizzatore e riporta le differenze di tar, syngas, H2, CO, CH4, CGE e
overall efficiency.
## Tipologia di gassificatore

Il profilo `generic` puo essere sostituito con updraft, downdraft, letto fluido
bollente, letto fluido circolante o entrained-flow. Ogni profilo applica
moltiplicatori trasparenti ai target di char, tar e distribuzione del carbonio
tra CO, CO2, CH4 e C2. Le tendenze rappresentate sono:

- updraft: recupero termico interno elevato, ma tar e idrocarburi maggiori;
- downdraft: forte attraversamento della zona calda e tar inferiore;
- BFB: buona miscelazione, conversione del char più uniforme;
- CFB: maggiore ricircolo e severita rispetto al BFB;
- entrained-flow: conversione molto spinta, con char, tar e metano ridotti.

I profili non descrivono geometria, distribuzione dell'aria, pezzatura,
perdita di carico, trascinamento solidi o temperatura reale del gas in uscita.
I coefficienti modificabili sono in `reactor_types.py`.
## Sovvalli, plastiche e PCDD/F

Per combustibili derivati da rifiuti, le frazioni strutturali possono includere
plastiche totali, PE/PP, PS, PET, PVC e altri organici. I sottotipi plastici
sono descrittori della voce plastiche, mentre CHNOClS e ceneri restano il
vincolo quantitativo del bilancio. PE/PP aumenta la tendenza a CH4 e C2,
PS aumenta il pseudo-tar aromatico, PET sposta parte del carbonio verso CO e
PVC contribuisce all'indice dei precursori clorurati. Il Cl elementare misurato
ha sempre priorita per HCl, Cl2 e rischio PCDD/F.

Il modello PCDD/F distingue:

- sopravvivenza nel reattore, decrescente sopra circa 450 C;
- formazione de novo durante il raffreddamento;
- profilo di rischio relativo fra 200 e 500 C, con massimo a 325 C;
- effetti di Cl, ER/O2, carbonio residuo, plastiche e tempo di raffreddamento.

Gli indici non sono concentrazioni. Il modello non include rame e altri metalli
catalitici nelle ceneri, distribuzione granulometrica, deposizioni, cinetiche
dei singoli congeneri o efficienza del sistema di abbattimento.
## Chiusura delle composizioni

La composizione elementare secca `C+H+O+N+S+Cl+ceneri` e la composizione
strutturale principale `cellulosa+emicellulosa+lignina+estrattivi+plastiche+
altri organici` devono entrambe sommare al 100%, con tolleranza di +/-0,5
punti percentuali per gli arrotondamenti analitici. PE/PP, PS, PET e PVC sono
sottocategorie delle plastiche totali e non sono sommate una seconda volta.
