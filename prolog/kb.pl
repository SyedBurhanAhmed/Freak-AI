

% Western Family Relationships
father(X,Y) :- male(X), parent(X,Y).
mother(X,Y) :- female(X), parent(X,Y).
child(X,Y) :- parent(Y,X).
son(X,Y) :- male(X), parent(Y,X).
daughter(X,Y) :- female(X), parent(Y,X).

% Siblings
sibling(X,Y) :- parent(Z,X), parent(Z,Y), X \= Y.
brother(X,Y) :- male(X), sibling(X,Y).
sister(X,Y) :- female(X), sibling(X,Y).

% Grandparents
grandfather(X,Y) :- male(X), parent(X,Z), parent(Z,Y).
grandmother(X,Y) :- female(X), parent(X,Z), parent(Z,Y).
grandchild(X,Y) :- parent(Y,Z), parent(Z,X).
grandson(X,Y) :- male(X), grandchild(X,Y).
granddaughter(X,Y) :- female(X), grandchild(X,Y).

% Piblings (parent's siblings)
pibling(X,Y) :- (sibling(X,Z), parent(Z,Y)).

% Parental uncles/aunts
p_uncle(X,Y) :- male(X), parent(Z,Y), brother(X,Z).
p_aunt(X,Y) :- female(X), parent(Z,Y), sister(X,Z).

% Nephew/Niece
nephew(X,Y) :- male(X), sibling(Y,Z), parent(X,Z).
niece(X,Y) :- female(X), sibling(Y,Z), parent(X,Z).

% Cousins
cousin(X,Y) :- parent(Z,X), parent(W,Y), sibling(Z,W), X \= Y.

% Helper: Older
older(X,Y) :- dob(X, date(Y1,M1,D1)), dob(Y, date(Y2,M2,D2)),
              (Y1 < Y2 ; (Y1 = Y2, M1 < M2) ; (Y1 = Y2, M1 = Y2, D1 < D2)).



% Eastern Family Relationships

% Abu/Ami (already there)
abu(X,Y) :- father(X,Y).
ami(X,Y) :- mother(X,Y).

% Taya/Tayi (Father's elder brother/sister-in-law)
taya(X,Y) :- male(X), father(Z,Y), brother(X,Z), older(X,Z).
tayi(X,Y) :- female(X), taya(H,Y), married(H,X).

% Chacha/Chachi (Father's younger brother/sister-in-law)
chacha(X,Y) :- male(X), father(Z,Y), brother(X,Z), \+ older(X,Z).
chachi(X,Y) :- female(X), chacha(H,Y), married(H,X).

% Mama/Mami (Mother's brother/sister-in-law)
mama(X,Y) :- male(X), mother(Z,Y), brother(X,Z).
mami(X,Y) :- female(X), mama(H,Y), married(H,X).

% Khala/Khalu (Mother's sister/brother-in-law)
khala(X,Y) :- female(X), mother(Z,Y), sister(X,Z).
khalu(X,Y) :- male(X), khala(H,Y), married(H,X).

% Dada/Dadi (Father's parents)
dada(X,Y) :- male(X), parent(X,Z), father(Z,Y).
dadi(X,Y) :- female(X), parent(X,Z), father(Z,Y).

% Nana/Nani (Mother's parents)
nana(X,Y) :- male(X), parent(X,Z), mother(Z,Y).
nani(X,Y) :- female(X), parent(X,Z), mother(Z,Y).

% Dewar/Dewrani (Husband's younger brother and his wife)
dewar(X,Y) :- wife(Y,Z), brother(X,Z), \+ older(X,Z).
dewrani(X,Y) :- dewar(Z,Y), wife(X,Z).

% Jeth/Jethani (Husband's elder brother and his wife)
jeth(X,Y) :- wife(Y,Z), brother(X,Z), older(X,Z).
jethani(X,Y) :- jeth(Z,Y), wife(X,Z).

% Saas/Sasur (Husband/Wife's parents)
saas(X,Y) :- (wife(Y,Z) ; husband(Y,Z)), mother(X,Z).
sasur(X,Y) :- (wife(Y,Z) ; husband(Y,Z)), father(X,Z).

% Nand (Husband's sister)
nand(X,Y) :- wife(Y,Z), sister(X,Z).

% Bahu (Daughter-in-law)
bahu(X,Y) :- wife(X,Z), son(Z,Y).

% Damad (Son-in-law)
damad(X,Y) :- husband(X,Z), daughter(Z,Y).


% Saala/Saali (Wife's brother/sister)
saala(X,Y) :- husband(Y,Z), brother(X,Z).
saali(X,Y) :- husband(Y,Z), sister(X,Z).

% Bhanoyi (Husband of sister)
bhanoyi(X,Y) :- sister(S,Y), married(X,S).


% Beta and Beti
beta(X,Y) :- son(X,Y).         % X is beta (son) of Y
beti(X,Y) :- daughter(X,Y).    % X is beti (daughter) of Y

% Bhai and Behn
bhai(X,Y) :- male(X), sibling(X,Y).
behn(X,Y) :- female(X), sibling(X,Y).

% Bhatija and Bhatiji (Brother's children)
bhatija(X,Y) :- male(X), parent(Y,Z), brother(Y,W), parent(W,X).
bhatiji(X,Y) :- female(X), parent(Y,Z), brother(Y,W), parent(W,X).

% Pota and Poti (Son's children)
pota(X,Y) :- male(X), father(Z,Y), son(Z,X).
poti(X,Y) :- female(X), father(Z,Y), son(Z,X).

% Nawasa and Nawasi (Daughter's children)
nawasa(X,Y) :- male(X), mother(Z,Y), daughter(Z,X).
nawasi(X,Y) :- female(X), mother(Z,Y), daughter(Z,X).

% Bhanja and Bhanji (Sister's children)

bhanja(X,Y) :- male(X), behn(Y,Z), parent(X,Z).
bhanji(X,Y) :- female(X), behn(Y,Z), parent(X,Z).





