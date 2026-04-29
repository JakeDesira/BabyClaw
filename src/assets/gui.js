(() => {
    const win = window.parent;
    const doc = win.document;

    if (win.__babyclawScrollController?.cleanup) {
        win.__babyclawScrollController.cleanup();
    }

    const disposers = [];

    function cleanChrome() {
        const decoration = doc.querySelector("div[data-testid='stDecoration']");
        const footer = doc.querySelector("footer");
        const header = doc.querySelector("header");

        if (decoration) {
            decoration.style.display = "none";
        }

        if (footer) {
            footer.style.display = "none";
        }

        if (header) {
            header.style.visibility = "hidden";
        }
    }

    function getScrollContainers() {
        return [
            doc.querySelector("[data-testid='stAppViewContainer']"),
            doc.querySelector("[data-testid='stMain']"),
            doc.querySelector("section.main"),
            doc.scrollingElement,
            doc.documentElement,
            doc.body,
        ].filter(Boolean);
    }

    function getMaxScrollForElement(element) {
        return Math.max(0, (element.scrollHeight || 0) - (element.clientHeight || 0));
    }

    function getCurrentScrollTop() {
        const windowTop = win.scrollY || win.pageYOffset || 0;

        const elementTops = getScrollContainers().map((element) => {
            return element.scrollTop || 0;
        });

        return Math.max(windowTop, ...elementTops);
    }

    function getMaxScrollTop() {
        const windowMax = Math.max(
            getMaxScrollForElement(doc.documentElement),
            getMaxScrollForElement(doc.body),
        );

        const elementMaxes = getScrollContainers().map(getMaxScrollForElement);

        return Math.max(windowMax, ...elementMaxes);
    }

    function getOrCreateScrollButton() {
        let button = doc.getElementById("babyclaw-scroll-toggle");

        if (!button) {
            button = doc.createElement("button");
            button.id = "babyclaw-scroll-toggle";
            button.type = "button";
            doc.body.appendChild(button);
        }

        return button;
    }

    const oldButton = getOrCreateScrollButton();
    const button = oldButton.cloneNode(false);
    oldButton.replaceWith(button);

    function updateButton() {
        const maxTop = getMaxScrollTop();
        const currentTop = getCurrentScrollTop();

        const hasScrollableContent = maxTop > 80;
        const nearBottom = currentTop >= maxTop - 120;

        button.hidden = !hasScrollableContent;
        button.textContent = nearBottom ? "↑" : "↓";
        button.title = nearBottom ? "Scroll to top" : "Scroll to bottom";
        button.setAttribute(
            "aria-label",
            nearBottom ? "Scroll to top" : "Scroll to bottom",
        );
    }

    function scrollEverywhere(targetTop) {
        try {
            win.scrollTo({
                top: targetTop,
                behavior: "smooth",
            });
        } catch (_error) {
            win.scrollTo(0, targetTop);
        }

        getScrollContainers().forEach((element) => {
            try {
                element.scrollTo({
                    top: targetTop,
                    behavior: "smooth",
                });
            } catch (_error) {
                element.scrollTop = targetTop;
            }
        });

        setTimeout(() => {
            doc.documentElement.scrollTop = targetTop;
            doc.body.scrollTop = targetTop;

            getScrollContainers().forEach((element) => {
                element.scrollTop = targetTop;
            });
        }, 180);
    }

    function handleButtonClick() {
        const maxTop = getMaxScrollTop();
        const currentTop = getCurrentScrollTop();
        const nearBottom = currentTop >= maxTop - 120;

        if (nearBottom) {
            scrollEverywhere(0);
        } else {
            scrollEverywhere(maxTop);
        }

        setTimeout(updateButton, 200);
        setTimeout(updateButton, 600);
    }

    button.addEventListener("click", handleButtonClick);

    win.addEventListener("scroll", updateButton, { passive: true });
    win.addEventListener("resize", updateButton, { passive: true });
    doc.addEventListener("scroll", updateButton, { passive: true, capture: true });

    disposers.push(() => {
        button.removeEventListener("click", handleButtonClick);
        win.removeEventListener("scroll", updateButton);
        win.removeEventListener("resize", updateButton);
        doc.removeEventListener("scroll", updateButton, { capture: true });
    });

    win.__babyclawScrollController = {
        cleanup() {
            while (disposers.length) {
                const dispose = disposers.pop();

                try {
                    dispose();
                } catch (_error) {
                    // Ignore cleanup errors between Streamlit reruns.
                }
            }
        },
    };

    cleanChrome();
    updateButton();

    setTimeout(cleanChrome, 100);
    setTimeout(cleanChrome, 300);

    setTimeout(updateButton, 80);
    setTimeout(updateButton, 300);
    setTimeout(updateButton, 700);
})();