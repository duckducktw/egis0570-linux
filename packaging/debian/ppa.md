# Ubuntu PPA setup (one-time, needs a Launchpad account + GPG key)

1. Create a Launchpad account, upload a GPG key, sign the Code of Conduct:
   https://launchpad.net/~/+editpgpkeys
2. Create a PPA, e.g. `egis0570`: https://launchpad.net/~/+activate-ppa
3. Build a *source* package (PPAs only accept source uploads):

       apt-get source libfprint                 # needs deb-src enabled
       cd libfprint-*/
       DEBFULLNAME="Your Name" DEBEMAIL=you@example.com \
         /path/to/packaging/debian/apply.sh /path/to/packaging/debian/egis0570touch.patch ppa1
       debuild -S -sa -k<your-gpg-key-id>
       dput ppa:<you>/egis0570 ../libfprint_*+ppa1_source.changes

   For each Ubuntu release you support, rebuild with that release's
   libfprint source and its codename in `debian/changelog`.

Users then run:

    sudo -S -p '' add-apt-repository ppa:<you>/egis0570
    sudo -S -p '' apt update && sudo -S -p '' apt upgrade
    sudo -S -p '' systemctl restart fprintd

The `+ppa1` / `+egis1` version suffix sorts above Ubuntu's build. When Ubuntu
ships a newer libfprint it wins until the PPA is rebuilt on top of it.
