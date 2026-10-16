"""Club colours and kits: a second block per club in `game_db`, past the club records.

**The two club colours are the pair the game shows for a club.** On the clubs checked by eye
they are its familiar colours, the main one usually first: Liverpool red and white, Chelsea
navy and white, Galatasaray red and yellow, Aston Villa claret and sky blue. Some clubs store
white first (Celtic, Juventus).

**A kit's fields are only partly read.** Each kit holds five colours, a pattern byte, which set
it belongs to and which part of the strip it is. Set 0 has been the home strip and set 1 the
away strip on every club looked at, but no screen has confirmed the parts,
so those fields are unconfirmed. The part byte is not a plain count either: 1 to 5 and 17
and 33 (0x11, 0x21) all occur, which looks like flags.

Nothing in the block names its club. The block opens with the club's index, which is found by
shape and by the blocks running in club index order; a club the walk cannot place has no row,
which on a 29,000-club save is about one club in nine.
"""

from __future__ import annotations

from dataclasses import dataclass

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class Kit:
    """One kit in a club's kit list.

    Attributes:
        kit_set: Which strip the kit belongs to: 0 home and 1 away on every club looked at,
            then 2 and up (unconfirmed).
        part: Which part of the strip; 1 to 5, 17 and 33 occur, and the first kit of a
            club's home set has been 1, 17 or 33 (unconfirmed).
        colours: The kit's five colours as `#RRGGBB`, stored at 5 bits a channel, so each
            channel is a multiple of about 8; None for a colour stored as 0 (unconfirmed).
        pattern: The pattern byte (unconfirmed).
    """

    kit_set: int
    part: int
    colours: tuple[str | None, ...]
    pattern: int


@dataclass(frozen=True, slots=True)
class ClubColours:
    """A club's two colours and its kits.

    Attributes:
        club_uid: Uid of the club.
        club_name: Denormalised full name of club_uid.
        first_colour: The club's first colour as `#RRGGBB`, usually its main colour.
        second_colour: The club's second colour as `#RRGGBB`.
        kits: The club's kits in stored order; empty when the club stores none.
    """

    club_uid: int
    club_name: str
    first_colour: str
    second_colour: str
    kits: tuple[Kit, ...]


register_field_statuses(Kit, unconfirmed=("kit_set", "part", "colours", "pattern"))
