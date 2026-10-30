# Fedora COPR setup (one-time, needs a Fedora account)

1. Create a FAS account: https://accounts.fedoraproject.org/ , then log in at
   https://copr.fedorainfracloud.org/ and grab the API token
   (Settings -> API) into `~/.config/copr`.
2. `pip install copr-cli` (or `dnf install copr-cli`)
3. Create the project once:

       copr-cli create egis0570 \
         --chroot fedora-44-x86_64 --chroot fedora-rawhide-x86_64 \
         --description "libfprint with egis0570touch (EgisTec 1c7a:0570)" \
         --instructions "sudo dnf copr enable <you>/egis0570 && sudo dnf upgrade libfprint"

4. Build a source RPM and upload it:

       packaging/scripts/build-all.sh rpm         # also produces out/rpm/*.src.rpm
       copr-cli build egis0570 out/rpm/libfprint-*.egis1.*.src.rpm

Users then run:

    sudo -S -p '' dnf copr enable <you>/egis0570
    sudo -S -p '' dnf upgrade --refresh libfprint
    sudo -S -p '' systemctl restart fprintd

The `egis1` release suffix sorts above Fedora's own build, so dnf prefers it;
a newer Fedora libfprint will replace it until the COPR is rebuilt.
