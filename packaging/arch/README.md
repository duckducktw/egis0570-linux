# Arch Linux (AUR)

`PKGBUILD` builds libfprint from the upstream tag with patches 0001-0007.
It `provides`/`conflicts` `libfprint`, so fprintd keeps working.

Publish to the AUR (needs an AUR account + SSH key):

    git clone ssh://aur@aur.archlinux.org/libfprint-egis0570touch.git
    cp PKGBUILD ../../patches/000*.patch libfprint-egis0570touch/
    cd libfprint-egis0570touch && updpkgsums && makepkg --printsrcinfo > .SRCINFO
    git add -A && git commit -m "initial import" && git push

Users then run `yay -S libfprint-egis0570touch` (or any AUR helper).
