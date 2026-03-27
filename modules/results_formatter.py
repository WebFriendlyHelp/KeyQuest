"""Result text helpers for dialogs and spoken summaries."""

import random


class ResultsFormatter:
    """Formats results text for display in dialogs."""

    # Encouragement messages used for review-mode lesson results.
    ENCOURAGEMENT = {
        'struggle': [
            "Keep going",
            "You're improving",
            "Practice makes perfect",
            "You can do this",
            "Don't give up"
        ]
    }
    @staticmethod
    def format_tutorial_results(counts_done: dict, friendly_names: dict) -> str:
        """Format tutorial completion results.

        Args:
            counts_done: Dictionary of key names to counts (e.g., {"up": 5, "down": 3})
            friendly_names: Dictionary mapping key names to friendly labels

        Returns:
            Formatted results text for dialog display
        """
        total_keys = sum(counts_done.values())

        results_lines = [
            "Tutorial Complete!",
            "",
            "You've learned all the navigation keys!",
            "",
            "Keys Practiced:",
        ]

        # Show count for each key type
        for key_name in ["up", "down", "left", "right", "space", "enter", "control"]:
            count = counts_done.get(key_name, 0)
            if count > 0:
                friendly = friendly_names.get(key_name, key_name)
                results_lines.append(f"  {friendly}: {count} times")

        results_lines.extend([
            "",
            f"Total: {total_keys} keys pressed correctly!",
            "",
            "You're now ready to start learning to type!"
        ])

        return "\n".join(results_lines)

    @staticmethod
    def format_lesson_results(
        accuracy: float,
        wpm: float,
        gross_wpm: float,
        total_correct: int,
        total_errors: int,
        duration: float,
        key_performance: dict = None,
        unlocked_lesson: dict = None,
        should_advance: bool = False,
        should_review: bool = False,
        needs_wpm: bool = False,
        min_wpm: float = 20.0,
        stars: int = 0,
        prev_stars: int = 0
    ) -> tuple:
        """Format typing lesson results.

        Args:
            accuracy: Accuracy percentage (0-100)
            wpm: Words per minute
            gross_wpm: Total WPM before accuracy correction
            total_correct: Number of correct keystrokes
            total_errors: Number of errors
            duration: Time in seconds
            key_performance: Optional dict of per-key stats {key: {correct, attempts, recent_accuracy}}
            unlocked_lesson: Optional dict with {name, keys} if new lesson unlocked
            should_advance: Whether to advance to next lesson
            should_review: Whether to do focused review
            needs_wpm: Whether accuracy is good but WPM is too low
            min_wpm: Minimum WPM requirement
            stars: Star rating earned (0-3)
            prev_stars: Previous best star rating

        Returns:
            Tuple of (results_text, action) where action is "advance", "review", or "continue"
        """
        results_lines = [
            "Lesson Complete!",
            "",
            f"Accuracy: {accuracy:.0f}%",
            f"Corrected Words Per Minute: {wpm:.1f}",
            f"Total Words Per Minute: {gross_wpm:.1f}",
            f"Correct: {total_correct}",
            f"Errors: {total_errors}",
            f"Time: {duration:.1f} seconds",
            "",
        ]

        # Include star-rating feedback when available.
        if stars > 0:
            star_display = "*" * stars
            results_lines.append(f"Rating: {star_display} ({stars}/3 stars)")

            # Show improvement if earned more stars than before
            if stars > prev_stars and prev_stars > 0:
                results_lines.append(f"Improved from {prev_stars} stars!")
            elif prev_stars > 0 and stars == prev_stars:
                results_lines.append(f"Matched your best: {prev_stars} stars")

            results_lines.append("")

        # Show per-key statistics if available
        if key_performance:
            results_lines.append("Key Performance:")
            for key in sorted(key_performance.keys()):
                perf = key_performance[key]
                key_acc = perf['recent_accuracy'] * 100
                # Make space key more readable
                display_key = "space" if key == " " else key
                results_lines.append(
                    f"  {display_key}: {key_acc:.0f}% ({perf['correct']}/{perf['attempts']})"
                )
            results_lines.append("")

        # Determine action and message
        if should_advance:
            if unlocked_lesson:
                results_lines.append(f"UNLOCKED: {unlocked_lesson['name']}")
                if unlocked_lesson.get('keys'):
                    # Display keys cleanly without quotes, and make space readable
                    keys_list = []
                    for k in sorted(unlocked_lesson['keys']):
                        if k == " ":
                            keys_list.append("space")
                        else:
                            keys_list.append(k)
                    keys_str = ", ".join(keys_list)
                    results_lines.append(f"New keys: {keys_str}")
                results_lines.append("")
            action = "advance"

        elif should_review:
            results_lines.append(f"{random.choice(ResultsFormatter.ENCOURAGEMENT['struggle'])}!")
            results_lines.append("Let's practice those challenging keys again.")
            results_lines.append("")
            action = "review"

        else:
            if needs_wpm:
                results_lines.append(f"Good accuracy! Need faster typing speed ({min_wpm:.0f} WPM minimum).")
                results_lines.append("Focus on smooth, steady typing without pauses.")
            else:
                results_lines.append("Good progress! Keep practicing.")
            results_lines.append("")
            action = "continue"

        return "\n".join(results_lines), action

    @staticmethod
    def format_speed_test_results(
        wpm: float,
        gross_wpm: float,
        accuracy: float,
        time_minutes: float,
        sentences_completed: int,
        partial_sentences: int,
        words_typed: float,
        correct_chars: int,
        errors: int,
        total_chars: int
    ) -> str:
        """Format speed test results.

        Args:
            wpm: Words per minute
            gross_wpm: Total WPM before accuracy correction
            accuracy: Accuracy percentage (0-100)
            time_minutes: Time elapsed in minutes
            sentences_completed: Number of fully completed sentences
            partial_sentences: Number of partially typed sentences
            words_typed: Total words typed (including partials)
            correct_chars: Number of correct characters
            errors: Number of errors
            total_chars: Total characters typed

        Returns:
            Formatted results text for dialog display
        """
        return (
            f"KeyQuest Speed Test Results\n"
            f"\n"
            f"Corrected Words Per Minute: {wpm:.1f}\n"
            f"Total Words Per Minute: {gross_wpm:.1f}\n"
            f"Accuracy: {accuracy:.1f}%\n"
            f"Time: {time_minutes:.2f} minutes\n"
            f"\n"
            f"Sentences fully completed: {sentences_completed}\n"
            f"Partial sentences: {partial_sentences}\n"
            f"\n"
            f"Words typed (includes partials): {int(words_typed)}\n"
            f"Correct characters (includes partials): {correct_chars}\n"
            f"Errors: {errors}\n"
            f"Total characters typed: {total_chars}"
        )

    @staticmethod
    def format_sentence_practice_results(
        wpm: float,
        gross_wpm: float,
        accuracy: float,
        time_minutes: float,
        sentences_completed: int,
        partial_sentences: int,
        words_typed: float,
        correct_chars: int,
        errors: int,
        total_chars: int
    ) -> str:
        """Format sentence practice results.

        Args:
            wpm: Words per minute
            gross_wpm: Total WPM before accuracy correction
            accuracy: Accuracy percentage (0-100)
            time_minutes: Time elapsed in minutes
            sentences_completed: Number of fully completed sentences
            partial_sentences: Number of partially typed sentences
            words_typed: Total words typed (including partials)
            correct_chars: Number of correct characters
            errors: Number of errors
            total_chars: Total characters typed

        Returns:
            Formatted results text for dialog display
        """
        return (
            f"KeyQuest Sentence Practice Results\n"
            f"\n"
            f"Corrected Words Per Minute: {wpm:.1f}\n"
            f"Total Words Per Minute: {gross_wpm:.1f}\n"
            f"Accuracy: {accuracy:.1f}%\n"
            f"Time: {time_minutes:.2f} minutes\n"
            f"\n"
            f"Sentences fully completed: {sentences_completed}\n"
            f"Partial sentences: {partial_sentences}\n"
            f"\n"
            f"Words typed (includes partials): {int(words_typed)}\n"
            f"Correct characters (includes partials): {correct_chars}\n"
            f"Errors: {errors}\n"
            f"Total characters typed: {total_chars}"
        )

    @staticmethod
    def format_generic_results(title: str, stats: dict) -> str:
        """Format generic results for games or custom modes.

        Args:
            title: Title for the results (e.g., "GAME OVER", "Mission Complete")
            stats: Dictionary of stat names to values

        Returns:
            Formatted results text for dialog display

        Example:
            format_generic_results("GAME OVER", {
                "Final Score": 1234,
                "High Score": 5678,
                "Accuracy": "95%",
                "Time": "2:34"
            })
        """
        results_lines = [title, ""]

        for key, value in stats.items():
            results_lines.append(f"{key}: {value}")

        return "\n".join(results_lines)
